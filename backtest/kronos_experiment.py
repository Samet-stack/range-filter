"""Bounded, reproducible crypto fine-tuning with causal splits and a held-out diagnostic.

The 2026 period has already been inspected in this project: it is NOT a fresh blind test.
Checkpoint selection uses Nov-Dec 2025 forecasts, never the 2026 diagnostic.
No automatic promotion to the terminal's default model.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from kronos_runtime import BASE_MODEL, CONTEXT, EXPERIMENT, HORIZON, KRONOS_ROOT, TOKENIZER, gpu_slot
from crypto_data import COLUMNS, DATA, SYMBOLS, validate_frame

VAL_START = pd.Timestamp("2025-11-01", tz="UTC")
TEST_START = pd.Timestamp("2026-01-01", tz="UTC")


def anchors(frame, step, lo, hi):
    """All context+target bars contiguous, all target timestamps strictly within the split."""
    ts = frame.timestamps.astype("int64").to_numpy() // 1_000_000
    gaps = np.r_[0, np.cumsum(np.diff(ts) != step)]
    out = []
    for i in range(CONTEXT - 1, len(frame) - HORIZON):
        if (frame.timestamps.iloc[i + 1] >= lo and frame.timestamps.iloc[i + HORIZON] < hi and
                gaps[i + HORIZON] == gaps[i - CONTEXT + 1]):
            out.append(i)
    return np.array(out, dtype=int)


def sparse_starts(indices, count):
    # Non-overlapping outcomes, then deterministic coverage across the whole date interval.
    spaced = []
    for i in indices:
        if not spaced or i - spaced[-1] >= HORIZON:
            spaced.append(int(i))
    if not spaced:
        raise ValueError("Pas assez de données pour cette période.")
    return [spaced[i] for i in np.linspace(0, len(spaced) - 1, min(count, len(spaced)), dtype=int)]


def normalize_window(window):
    # Match inference: statistics are computed on the observed context only.
    context = window[:CONTEXT]
    return np.clip((window - context.mean(0)) / (context.std(0) + 1e-5), -5, 5).astype(np.float32)


def load_data(validation_points, diagnostic_points):
    groups, train, validation, diagnostic = [], [], [], []
    for tf in ("1h", "4h"):
        step = (1 if tf == "1h" else 4) * 3_600_000
        for sym in SYMBOLS:
            frame = pd.read_csv(DATA / f"{sym}_{tf}.csv")
            frame.timestamps = pd.to_datetime(frame.timestamps, utc=True)
            validate_frame(frame)
            ts = frame.timestamps.dt
            stamps = np.stack([ts.minute, ts.hour, ts.weekday, ts.day, ts.month], axis=1).astype(np.float32)
            group = dict(sym=sym, tf=tf, frame=frame, values=frame[COLUMNS[1:]].to_numpy(dtype=np.float32), stamps=stamps)
            k = len(groups)
            groups.append(group)
            end = frame.timestamps.iloc[-1] + pd.Timedelta(milliseconds=step)
            tr = anchors(frame, step, frame.timestamps.iloc[0], VAL_START)
            if not len(tr):
                raise ValueError(f"Pas de fenêtres d'entraînement : {sym} {tf}")
            train.append(tr)
            validation.extend((k, i) for i in sparse_starts(anchors(frame, step, VAL_START, TEST_START), validation_points))
            diagnostic.extend((k, i) for i in sparse_starts(anchors(frame, step, TEST_START, end), diagnostic_points))
    return groups, train, validation, diagnostic


def baseline(frame, i):
    """Same quantile/volatility method as the existing benchmark, past outcomes only."""
    c, h, l = (frame[x].to_numpy() for x in ("close", "high", "low"))
    ret = np.diff(np.log(c[:i + 1]))
    vols = np.lib.stride_tricks.sliding_window_view(ret, 48).std(axis=1)
    js = np.arange(48, i - HORIZON)
    v = vols[js - 48]
    highs = np.lib.stride_tricks.sliding_window_view(h, HORIZON)[js + 1].max(axis=1)
    lows = np.lib.stride_tricks.sliding_window_view(l, HORIZON)[js + 1].min(axis=1)
    valid = v > 0
    if not valid.any():
        raise ValueError("Historique sans volatilité pour la comparaison.")
    top = np.percentile((highs[valid] / c[js[valid]] - 1) / v[valid], 90) * vols[-1]
    bot = np.percentile((lows[valid] / c[js[valid]] - 1) / v[valid], 10) * vols[-1]
    return float(top), float(bot)


def metrics(rows):
    frame = pd.DataFrame(rows)
    out = {}
    for tf, a in frame.groupby("tf"):
        error_top = a.real_top - a.top
        error_bot = a.real_bot - a.bot
        loss = np.maximum(.9 * error_top, -.1 * error_top) + np.maximum(.1 * error_bot, -.9 * error_bot)
        nonzero = a.real_return != 0
        out[tf] = dict(n=len(a), range_error=float(loss.mean() * 1e4),
                       above_pct=float((error_top > 0).mean() * 100), below_pct=float((error_bot < 0).mean() * 100),
                       direction_pct=float(((a.pred_return[nonzero] > 0) == (a.real_return[nonzero] > 0)).mean() * 100))
    return out


def evaluate(predictor, groups, starts, volume, samples, seed, name, out):
    import torch
    rows = []
    predictor.model.eval()
    predictor.tokenizer.eval()
    # Kronos caches RoPE tensors. inference_mode would make those caches unusable
    # for the next training forward at the same sequence length (PyTorch 2.6).
    with torch.no_grad():
        for ordinal, (k, i) in enumerate(starts):
            g = groups[k]
            frame = g["frame"]
            hist = frame.iloc[i - CONTEXT + 1:i + 1]
            future = frame.iloc[i + 1:i + HORIZON + 1]
            cols = COLUMNS[1:] if volume else COLUMNS[1:5]
            x = hist[cols].reset_index(drop=True)
            xt = hist.timestamps.reset_index(drop=True)
            yt = future.timestamps.reset_index(drop=True)
            # Identical random seeds per case across compared checkpoints.
            torch.manual_seed(seed + ordinal)
            paths = []
            for offset in range(0, samples, 10):
                count = min(10, samples - offset)
                paths += predictor.predict_batch([x] * count, [xt] * count, [yt] * count, pred_len=HORIZON,
                                                  T=1.0, top_p=.9, sample_count=1, verbose=False)
            last = hist.close.iloc[-1]
            simple_top, simple_bot = baseline(frame, i)
            rows.append(dict(sym=g["sym"], tf=g["tf"], timestamp=hist.timestamps.iloc[-1].isoformat(),
                top=float(np.percentile([p.high.max() / last - 1 for p in paths], 90)),
                bot=float(np.percentile([p.low.min() / last - 1 for p in paths], 10)),
                pred_return=float(np.mean([p.close.iloc[-1] / last - 1 for p in paths])),
                real_top=float(future.high.max() / last - 1), real_bot=float(future.low.min() / last - 1),
                real_return=float(future.close.iloc[-1] / last - 1), simple_top=simple_top, simple_bot=simple_bot))
            if (ordinal + 1) % 16 == 0:
                print(f"{name}: {ordinal + 1}/{len(starts)} prévisions", flush=True)
    pd.DataFrame(rows).to_csv(out / f"{name}.csv", index=False)
    return rows


def write_report(report, out):
    report["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    path = out / "report.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    temporary.replace(path)


def run(args):
    import torch
    sys.path.insert(0, str(KRONOS_ROOT))
    from model import Kronos, KronosTokenizer, KronosPredictor
    out = args.output
    if out.exists():
        raise FileExistsError(f"Expérience déjà présente : {out}. Utiliser --output pour un nouvel essai.")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA indisponible ; aucun long entraînement CPU n'est lancé.")
    groups, train, validation, diagnostic = load_data(args.validation_points, args.diagnostic_points)
    out.mkdir(parents=True)
    report = dict(status="running", summary="V2 : entraînement avec volumes en cours. Aucun résultat validé pour le moment.",
        config={**vars(args), "output": str(out), "context": CONTEXT, "horizon": HORIZON,
                "train_before": VAL_START.isoformat(), "validation_before": TEST_START.isoformat(),
                "normalization": "observed_context_only", "loss": "next_12_tokens", "balanced_asset_timeframe": True},
        limitation="Diagnostic 2026 déjà consulté ; échantillon exploratoire, pas un test indépendant ni une preuve de rentabilité.",
        data=json.loads((DATA / "manifest.json").read_text()), epochs=[], diagnostic={})
    write_report(report, out)
    try:
        with gpu_slot():
            torch.manual_seed(args.seed)
            rng = np.random.default_rng(args.seed)
            tok = KronosTokenizer.from_pretrained(TOKENIZER).to("cuda:0").eval()
            mdl = Kronos.from_pretrained(BASE_MODEL).to("cuda:0")
            pred = KronosPredictor(mdl, tok, device="cuda:0", max_context=512)
            initial = evaluate(pred, groups, validation, True, args.samples, args.seed, "validation-epoch-0", out)
            best = sum(v["range_error"] for v in metrics(initial).values()) / 2
            best_epoch = 0
            mdl.save_pretrained(out / "best")
            report["epochs"].append(dict(epoch=0, validation=metrics(initial)))
            write_report(report, out)
            opt = torch.optim.AdamW(mdl.parameters(), lr=args.lr, betas=(.9, .95), weight_decay=.1)
            stale = 0
            for epoch in range(1, args.epochs + 1):
                mdl.train()
                losses = []
                started = time.monotonic()
                for offset in range(0, args.windows, args.batch):
                    xs, stamps = [], []
                    for _ in range(min(args.batch, args.windows - offset)):
                        k = int(rng.integers(len(groups)))
                        i = int(rng.choice(train[k]))
                        g = groups[k]
                        xs.append(normalize_window(g["values"][i - CONTEXT + 1:i + HORIZON + 1]))
                        stamps.append(g["stamps"][i - CONTEXT + 1:i + HORIZON + 1])
                    x = torch.from_numpy(np.stack(xs)).to("cuda:0")
                    stamp = torch.from_numpy(np.stack(stamps)).to("cuda:0")
                    with torch.no_grad():
                        z0, z1 = tok.encode(x, half=True)
                    logits = mdl(z0[:, :-1], z1[:, :-1], stamp[:, :-1])
                    loss = mdl.head.compute_loss(logits[0][:, -HORIZON:], logits[1][:, -HORIZON:],
                                                 z0[:, -HORIZON:], z1[:, -HORIZON:])[0]
                    if not torch.isfinite(loss):
                        raise ValueError("Perte d'entraînement non finie.")
                    opt.zero_grad(set_to_none=True)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(mdl.parameters(), 3.)
                    opt.step()
                    losses.append(loss.item())
                    if (offset // args.batch + 1) % 64 == 0:
                        print(f"Époque {epoch}: {offset + len(xs)}/{args.windows}, perte {np.mean(losses):.4f}", flush=True)
                val = evaluate(pred, groups, validation, True, args.samples, args.seed, f"validation-epoch-{epoch}", out)
                score = sum(v["range_error"] for v in metrics(val).values()) / 2
                improved = score < best
                if improved:
                    best, best_epoch, stale = score, epoch, 0
                    mdl.save_pretrained(out / "best")
                else:
                    stale += 1
                report["epochs"].append(dict(epoch=epoch, training_loss=float(np.mean(losses)), validation=metrics(val),
                                             seconds=round(time.monotonic() - started, 1)))
                report["best_epoch"] = best_epoch
                report["summary"] = f"V2 : époque {epoch}/{args.epochs} terminée, comparaison des prévisions en cours."
                write_report(report, out)
                print(f"Époque {epoch}: erreur fourchette validation={score:.2f}, retenue={best_epoch}", flush=True)
                if stale >= 2:
                    break
            # Release training allocations before loading each diagnostic model.
            del opt, mdl, pred, logits, loss, x, stamp, z0, z1
            torch.cuda.empty_cache()
            variants = [("original", BASE_MODEL, False), ("original-volume", BASE_MODEL, True),
                        ("crypto-v1", str(KRONOS_ROOT / "finetuned/crypto/best"), False),
                        ("crypto-v2", str(out / "best"), True)]
            for name, path, volume in variants:
                pred = KronosPredictor(Kronos.from_pretrained(path).eval(), tok, device="cuda:0", max_context=512)
                rows = evaluate(pred, groups, diagnostic, volume, args.samples, args.seed + 10000, f"diagnostic-{name}", out)
                report["diagnostic"][name] = metrics(rows)
                if "simple" not in report["diagnostic"]:
                    report["diagnostic"]["simple"] = metrics([dict(r, top=r["simple_top"], bot=r["simple_bot"], pred_return=0.) for r in rows])
                    for value in report["diagnostic"]["simple"].values():
                        value.pop("direction_pct")  # A range baseline does not predict direction.
                write_report(report, out)
                del pred
                torch.cuda.empty_cache()
            report["status"] = "complete"
            report["best_epoch"] = best_epoch
            report["weights_sha256"] = hashlib.sha256((out / "best/model.safetensors").read_bytes()).hexdigest()
            scores = report["diagnostic"]
            beats = all(scores["crypto-v2"][tf]["range_error"] < scores["simple"][tf]["range_error"] for tf in ("1h", "4h"))
            report["summary"] = ("V2 : essai exploratoire terminé. " +
                ("Fourchettes meilleures sur cet échantillon ; confirmation indépendante nécessaire." if beats else
                 "La méthode simple reste meilleure sur au moins une unité de temps. V2 reste expérimental."))
            write_report(report, out)
            print(json.dumps(report["diagnostic"], indent=2), flush=True)
    except BaseException as exc:
        report["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        report["summary"] = "V2 : expérience interrompue ; résultats incomplets."
        write_report(report, out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EXPERIMENT)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--windows", type=int, default=4096)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=4e-6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--validation-points", type=int, default=4)
    parser.add_argument("--diagnostic-points", type=int, default=12)
    args = parser.parse_args()
    if min(args.epochs, args.windows, args.batch, args.samples, args.validation_points, args.diagnostic_points) < 1:
        parser.error("Tous les nombres de calculs doivent être positifs.")
    run(args)


if __name__ == "__main__":
    main()
