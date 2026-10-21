"""Does Kronos (pretrained K-line model) add direction to our BUYs?
Test period 2026-01-01+ only: after the Kronos release (paper 2025-08), so the model
cannot have seen it. Results cached per asset in kronos_cache/ (rerun resumes). For each start bar (every BUY, and every 5th bar as reference),
Kronos-small forecasts the next H bars from the last 400 closed bars (OHLC, no volume).
Outcome = the Pine test: +x% before -x% from the start close (same bar touching both = down).
Usage: ~/kronos/.venv/bin/python -I kronos_test.py [4h,1h]   (reads data/ and data1h/)"""
import math, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path.home() / "kronos"))
import numpy as np, pandas as pd, torch
import rf_bt
from indicator_stats import moves
from model import Kronos, KronosTokenizer, KronosPredictor

T2026 = 1767225600000
CTX, H, EVERY, CAP, BATCH, SAMPLES = 400, 12, 5, 300, 32, 5
TFS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["4h", "1h"]
HERE = Path(__file__).parent

def first_hit(h, l, c, i, x):
    up, dn = c[i] * (1 + x), c[i] * (1 - x)
    for j in range(i + 1, min(i + 1 + CAP, len(c))):
        if l[j] <= dn: return 0
        if h[j] >= up: return 1
    return None

def z2(a, b):  # two-proportion z, a/b = lists of 0/1
    if len(a) < 5 or len(b) < 5: return float("nan")
    p1, p0 = sum(a) / len(a), sum(b) / len(b); p = (sum(a) + sum(b)) / (len(a) + len(b))
    se = math.sqrt(p * (1 - p) * (1 / len(a) + 1 / len(b)))
    return (p1 - p0) / se if se > 0 else float("nan")

torch.manual_seed(0); np.random.seed(0)
tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
mdl = Kronos.from_pretrained("NeoQuasar/Kronos-small")
pred = KronosPredictor(mdl, tok, device="cuda:0" if torch.cuda.is_available() else "cpu", max_context=512)

rows = []
for tf, sub in [(x, {"4h": "data", "1h": "data1h"}[x]) for x in TFS]:
    rf_bt.DATA = HERE / sub
    for sym in ("BTC", "ETH", "ZEC", "HYPE"):
        if not (rf_bt.DATA / f"{sym}.csv").exists(): continue
        bars = rf_bt.load(sym)
        t = [b[0] for b in bars]; o = [b[1] for b in bars]; h = [b[2] for b in bars]; l = [b[3] for b in bars]; c = [b[4] for b in bars]
        dt = t[1] - t[0]
        out, _ = moves(bars, samples=0, start=T2026)
        idx = {v: k for k, v in enumerate(t)}
        buys = {idx[m["t"]] for m in out}
        # Open moves at the data end are not in `out`; they are BUYs too but unresolved, skip.
        starts = sorted(buys | {i for i in range(len(t)) if t[i] >= T2026 and i % EVERY == 0})
        starts = [i for i in starts if i >= CTX - 1 and i + H < len(t)]
        df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c})
        ts = pd.Series(pd.to_datetime(t, unit="ms"))
        cache = HERE / "kronos_cache" / f"{tf}_{sym}.csv"
        if cache.exists():
            rows += pd.read_csv(cache).to_dict("records"); print(tf, sym, "cache", flush=True); continue
        mine = []; t0 = time.time()
        for b0 in range(0, len(starts), BATCH):
            chunk = starts[b0:b0 + BATCH]
            dfs = [df.iloc[i - CTX + 1:i + 1].reset_index(drop=True) for i in chunk]
            xts = [ts.iloc[i - CTX + 1:i + 1].reset_index(drop=True) for i in chunk]
            yts = [pd.Series(pd.to_datetime([t[i] + k * dt for k in range(1, H + 1)], unit="ms")) for i in chunk]
            ps = pred.predict_batch(dfs, xts, yts, pred_len=H, T=1.0, top_p=0.9, sample_count=SAMPLES, verbose=False)
            for i, p in zip(chunk, ps):
                mine.append(dict(tf=tf, sym=sym, i=i, buy=i in buys,
                                 k_ret=p["close"].iloc[-1] / c[i] - 1, k_max=p["high"].max() / c[i] - 1,
                                 real_ret=c[i + H] / c[i] - 1,
                                 up2=first_hit(h, l, c, i, 0.02), up3=first_hit(h, l, c, i, 0.03)))
            done = min(b0 + BATCH, len(starts)); el = time.time() - t0
            print(f"{tf} {sym} {done}/{len(starts)}  {el:.0f}s, reste ~{el / done * (len(starts) - done):.0f}s", flush=True)
        cache.parent.mkdir(exist_ok=True); pd.DataFrame(mine).to_csv(cache, index=False); rows += mine
        print(tf, sym, "starts", len(starts), "BUY", len(buys), flush=True)

R = pd.DataFrame(rows)

print("\n1) Kronos alone, reference bars: does 'Kronos says up' give +x% before -x% more often?")
print("2) Our BUYs: BUYs Kronos likes vs BUYs Kronos dislikes.  z >= 2 = real, |z| < 2 = noise.\n")
for tf in TFS:
    for x in ("up2", "up3"):
        A = R[(R.tf == tf) & R[x].notna()]
        ref, buy = A[~A.buy], A[A.buy]
        ru, rd = ref[ref.k_ret > 0][x].tolist(), ref[ref.k_ret <= 0][x].tolist()
        bu, bd = buy[buy.k_ret > 0][x].tolist(), buy[buy.k_ret <= 0][x].tolist()
        ic = ref["k_ret"].rank().corr(ref["real_ret"].rank())  # Spearman without scipy
        f = lambda v: f"{100 * np.mean(v):4.0f}% (n={len(v)})" if v else "  n/a"
        print(f"{tf} +{x[2]}% avant -{x[2]}% | ref: Kronos hausse {f(ru)} vs baisse {f(rd)} z={z2(ru, rd):+.1f} | "
              f"BUY: Kronos hausse {f(bu)} vs baisse {f(bd)} z={z2(bu, bd):+.1f} | IC({H}b)={ic:+.3f}")
