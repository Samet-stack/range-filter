"""Is Kronos's probable range (high/low over the next H bars) right, and better than a simple method?
Test period 2026-01-01+ (after the Kronos release). Starts every STEP bars (non-overlapping windows).
Kronos: PATHS imagined paths; top = 90th pct of path max-high, bottom = 10th pct of path min-low
(as in kronos_live.py). Simple method: past windows' max-high / min-low moves, scaled by the
current volatility (std of the last 48 one-bar log returns), 90th / 10th pct, past data only.
Scores: how often reality breaks above top / below bottom (ideal 10 % each), pinball loss
(lower = better), and rank correlation of predicted width vs realised width.
Usage: ~/kronos/.venv/bin/python -I kronos_range_test.py"""
import math, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path.home() / "kronos"))
import numpy as np, pandas as pd, torch
import rf_bt
from model import Kronos, KronosTokenizer, KronosPredictor

T2026 = 1767225600000
CTX, H, PATHS, BATCH = 400, 12, 16, 128
PLAN = (("4h", "data", 20), ("1h", "data1h", 40))  # (timeframe, folder, STEP)
HERE = Path(__file__).parent
# KRONOS_MODEL=~/kronos/finetuned/crypto/best to test the fine-tuned model (separate result files).
MODEL = os.environ.get("KRONOS_MODEL", "NeoQuasar/Kronos-small")
SUF = "" if MODEL == "NeoQuasar/Kronos-small" else "_ft"

torch.manual_seed(0); np.random.seed(0)
pred = KronosPredictor(Kronos.from_pretrained(MODEL),
                       KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base"),
                       device="cuda:0" if torch.cuda.is_available() else "cpu", max_context=512)

def vol(c, i, n=48):
    r = np.diff(np.log(c[i - n:i + 1]))
    return r.std()

rows = []
for tf, sub, step in PLAN:
    rf_bt.DATA = HERE / sub
    for sym in ("BTC", "ETH", "ZEC", "HYPE"):
        bars = rf_bt.load(sym)
        t = np.array([b[0] for b in bars]); o, h, l, c = (np.array([b[k] for b in bars]) for k in (1, 2, 3, 4))
        dt = int(t[1] - t[0])
        starts = [i for i in range(CTX, len(t) - H) if t[i] >= T2026 and i % step == 0]
        df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c})
        ts = pd.Series(pd.to_datetime(t, unit="ms"))
        # Normalised forward moves for every past bar (used by the simple method, past only).
        fu = np.full(len(c), np.nan); fd = np.full(len(c), np.nan); vz = np.full(len(c), np.nan)
        for i in range(48, len(c) - H):
            vz[i] = vol(c, i)
            fu[i] = (h[i + 1:i + H + 1].max() / c[i] - 1) / vz[i]
            fd[i] = (l[i + 1:i + H + 1].min() / c[i] - 1) / vz[i]
        t0 = time.time(); per = BATCH // PATHS
        for b0 in range(0, len(starts), per):
            chunk = starts[b0:b0 + per]
            dfs, xts, yts = [], [], []
            for i in chunk:
                d = df.iloc[i - CTX + 1:i + 1].reset_index(drop=True); x = ts.iloc[i - CTX + 1:i + 1].reset_index(drop=True)
                y = pd.Series(pd.to_datetime([int(t[i]) + k * dt for k in range(1, H + 1)], unit="ms"))
                dfs += [d] * PATHS; xts += [x] * PATHS; yts += [y] * PATHS
            ps = pred.predict_batch(dfs, xts, yts, pred_len=H, T=1.0, top_p=0.9, sample_count=1, verbose=False)
            for k, i in enumerate(chunk):
                g = ps[k * PATHS:(k + 1) * PATHS]
                mx = np.array([p["high"].max() for p in g]) / c[i] - 1
                mn = np.array([p["low"].min() for p in g]) / c[i] - 1
                past = slice(48, i - H)  # windows fully closed before bar i
                v = vol(c, i)
                rows.append(dict(tf=tf, sym=sym,
                                 k_top=np.percentile(mx, 90), k_bot=np.percentile(mn, 10),
                                 s_top=np.nanpercentile(fu[past], 90) * v, s_bot=np.nanpercentile(fd[past], 10) * v,
                                 r_top=h[i + 1:i + H + 1].max() / c[i] - 1, r_bot=l[i + 1:i + H + 1].min() / c[i] - 1))
        print(f"{tf} {sym}: {len(starts)} departs, {time.time() - t0:.0f}s", flush=True)

R = pd.DataFrame(rows); R.to_csv(HERE / f"kronos_range{SUF}.csv", index=False)

def pinball(y, q, tau):
    d = y - q
    return np.mean(np.maximum(tau * d, (tau - 1) * d))

print(f"\nHorizon {H} bougies. Ideal : 10 % au-dessus du haut, 10 % sous le bas. Erreur : plus bas = mieux.")
for tf in ("4h", "1h"):
    A = R[R.tf == tf]
    for who, lab in (("k", "Kronos       "), ("s", "Methode simple")):
        above = 100 * (A.r_top > A[f"{who}_top"]).mean(); below = 100 * (A.r_bot < A[f"{who}_bot"]).mean()
        err = 1e4 * (pinball(A.r_top, A[f"{who}_top"], 0.9) + pinball(A.r_bot, A[f"{who}_bot"], 0.1))
        w, rw = A[f"{who}_top"] - A[f"{who}_bot"], A.r_top - A.r_bot
        print(f"{tf} {lab} | casse le haut {above:4.1f} %  casse le bas {below:4.1f} %  | erreur {err:6.1f} | "
              f"largeur moy {100 * w.mean():4.1f} %  | lien largeur prevue/reelle {w.rank().corr(rw.rank()):+.2f}  (n={len(A)})")
