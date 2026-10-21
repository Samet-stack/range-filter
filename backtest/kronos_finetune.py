"""Fine-tune Kronos-small (predictor only, pretrained tokenizer frozen) on our crypto candles.
Train: BTC/ETH/ZEC/HYPE 1h + 4h up to 2025-10-31. Validation (pick the best epoch):
2025-11-01 .. 2025-12-31. 2026 is never seen: it stays the test period of kronos_test.py and
kronos_range_test.py. Windows never cross two series. No volume in our data: zeros, as at test time.
Training recipe follows Kronos's finetune_csv (window-wide normalisation, clip 5, AdamW, OneCycle).
Usage: ~/kronos/.venv/bin/python -I kronos_finetune.py   -> ~/kronos/finetuned/crypto/best"""
import math, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path.home() / "kronos"))
import numpy as np, pandas as pd, torch
import rf_bt
from model import Kronos, KronosTokenizer

T_VAL, T_TEST = 1761955200000, 1767225600000  # 2025-11-01, 2026-01-01 UTC
CTX, H = 400, 12
WIN = CTX + H + 1
EPOCHS, PER_EPOCH, BATCH, LR = 5, 30000, 32, 4e-6
OUT = Path.home() / "kronos" / "finetuned" / "crypto"
HERE = Path(__file__).parent
torch.manual_seed(0); random.seed(0); np.random.seed(0)
dev = "cuda:0"

def series():
    for sub in ("data", "data1h"):
        rf_bt.DATA = HERE / sub
        for s in ("BTC", "ETH", "ZEC", "HYPE"):
            b = rf_bt.load(s)
            t = pd.to_datetime([x[0] for x in b], unit="ms")
            f = np.zeros((len(b), 6), np.float32); f[:, :4] = [x[1:5] for x in b]
            st = np.stack([t.minute, t.hour, t.weekday, t.day, t.month], 1).astype(np.float32)
            yield np.array([x[0] for x in b]), f, st

def windows(lo, hi):  # (series, start) with the whole window inside [lo, hi)
    out = []
    for k, (t, f, st) in enumerate(S):
        idx = np.nonzero((t >= lo) & (t < hi))[0]
        if len(idx) >= WIN:
            out += [(k, i) for i in range(idx[0], idx[-1] - WIN + 2)]
    return out

def batch(items):
    xs, ss = [], []
    for k, i in items:
        x = S[k][1][i:i + WIN]; m, sd = x.mean(0), x.std(0)
        xs.append(np.clip((x - m) / (sd + 1e-5), -5, 5)); ss.append(S[k][2][i:i + WIN])
    return torch.from_numpy(np.stack(xs)).to(dev), torch.from_numpy(np.stack(ss)).to(dev)

def loss_on(model, tok, items):
    x, st = batch(items)
    with torch.no_grad():
        z0, z1 = tok.encode(x, half=True)
    lg = model(z0[:, :-1], z1[:, :-1], st[:, :-1, :])
    return model.head.compute_loss(lg[0], lg[1], z0[:, 1:], z1[:, 1:])[0]

S = list(series())
train, val = windows(0, T_VAL), windows(T_VAL, T_TEST)[::7]
print(f"fenetres : entrainement {len(train)}, validation {len(val)}", flush=True)
tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base").to(dev).eval()
model = Kronos.from_pretrained("NeoQuasar/Kronos-small").to(dev)

def val_loss():
    model.eval(); tot = 0.0
    with torch.no_grad():
        for b in range(0, len(val), 64):
            tot += loss_on(model, tok, val[b:b + 64]).item() * len(val[b:b + 64])
    model.train(); return tot / len(val)

best = val_loss(); print(f"avant entrainement : erreur validation {best:.4f}", flush=True)
OUT.mkdir(parents=True, exist_ok=True); model.save_pretrained(OUT / "best")
opt = torch.optim.AdamW(model.parameters(), lr=LR, betas=(0.9, 0.95), weight_decay=0.1)
steps = PER_EPOCH // BATCH
sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, steps_per_epoch=steps, epochs=EPOCHS, pct_start=0.03, div_factor=10)
model.train()
for ep in range(EPOCHS):
    t0 = time.time(); random.shuffle(train); run = 0.0
    for s in range(steps):
        loss = loss_on(model, tok, train[s * BATCH:(s + 1) * BATCH])
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 3.0); opt.step(); sched.step()
        run += loss.item()
    v = val_loss()
    tag = ""
    if v < best:
        best = v; model.save_pretrained(OUT / "best"); tag = "  <- meilleur, sauve"
    print(f"epoque {ep + 1}/{EPOCHS} : erreur entrainement {run / steps:.4f}, validation {v:.4f}, {time.time() - t0:.0f}s{tag}", flush=True)
print(f"modele : {OUT / 'best'}  (validation {best:.4f})")
