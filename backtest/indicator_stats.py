"""Python replica of range-filter-manuel.pine statistics (default inputs), for comparison
with the TradingView table. Usage: python3 indicator_stats.py"""
import os, sys, statistics as st
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rf_bt
from rf_bt import ema, rma, simulate, T2024

def moves(bars, period=100, mult=3.0, atr_len=14, atr_floor=0.25, range_bars=20, fee_rt=0.002, samples=20, start=T2024):
    t = [b[0] for b in bars]; h = [b[2] for b in bars]; l = [b[3] for b in bars]; c = [b[4] for b in bars]; n = len(bars)
    raw = [None] + [abs(c[i] - c[i - 1]) for i in range(1, n)]
    second = ema(ema(raw, period), period * 2 - 1)
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, n)]
    atr = rma(tr, atr_len); warm = max(period * 3, atr_len)
    filt = None; flat = 0; last_dir = 0; last_src = None
    in_move = False; out = []; base = []; rng = 42.0
    for i in range(n):
        step = 0
        width = max(second[i] * mult, atr[i] * atr_floor) if second[i] is not None and atr[i] is not None else None
        ready = i >= 1 and width is not None and i >= warm
        if not ready:
            filt = None; flat = 0; last_dir = 0; last_src = None
        else:
            pf = c[i] if filt is None else filt
            cand = max(pf, c[i] - width) if c[i] > pf else min(pf, c[i] + width)
            sup = (c[i] > c[i - 1]) if cand > pf else (c[i] < c[i - 1]) if cand < pf else True
            filt = cand if sup else pf
            step = 1 if filt > pf else -1 if filt < pf else 0
            if step and step == last_dir and not (c[i] > last_src if step == 1 else c[i] < last_src):
                filt = pf; step = 0
            if step:
                last_dir = step; last_src = c[i]
            flat = flat + 1 if step == 0 else 0
        if in_move:
            if h[i] / ref - 1 > mfe:
                mae_pk = mae; mfe = h[i] / ref - 1
            mae = min(mae, l[i] / ref - 1)
            if step == -1 or flat >= range_bars:
                in_move = False; dur = i - b0
                if t[b0] >= start:
                    out.append(dict(t=t[b0], mfe=mfe, mae_pk=mae_pk, res=c[i] / ref - 1 - fee_rt, dur=dur))
                    max_back = min(4900, i - warm)
                    if samples and max_back > dur + 1:
                        for _ in range(samples):
                            rng = (rng * 16807.0) % 2147483647.0
                            o = dur + 1 + int(rng / 2147483647.0 * (max_back - dur))
                            r0 = c[i - o]; hi = max(h[i - o + j] for j in range(1, dur + 1))
                            base.append(dict(mfe=max(0.0, hi / r0 - 1), res=c[i - o + dur] / r0 - 1 - fee_rt))
        elif ready and step == 1:
            in_move = True; ref = c[i]; b0 = i; mfe = mae = mae_pk = 0.0
    return out, base

def table(name, out, base):
    def share(a, x): return 100 * sum(v >= x for v in a) / len(a)
    m = [x["mfe"] for x in out]; bm = [x["mfe"] for x in base]
    print(f"{name:9s} n={len(out):4d} | max med {100*st.median(m):5.2f}% (hasard {100*st.median(bm):5.2f}) | "
          + " ".join(f">={k}%: {share(m, k/100):3.0f}% ({share(bm, k/100):3.0f})" for k in (2, 3, 5))
          + f" | baisse avant max {100*st.median(x['mae_pk'] for x in out):+5.2f}% | a FIN {100*st.mean(x['res'] for x in out):+5.2f}% (hasard {100*st.mean(x['res'] for x in base):+5.2f}) | duree {st.median(x['dur'] for x in out):.0f} b")

if __name__ == "__main__":
    for tf, d in (("1h", "data1h"), ("4h", "data")):
        rf_bt.DATA = Path(__file__).parent / d
        for s in ("BTC", "ETH", "ZEC", "HYPE"):
            bars = rf_bt.load(s)
            out, base = moves(bars)
            ctl, _ = simulate(bars, control=True)
            # Same BUYs as the V4 control entries (validated against TradingView), open move excluded.
            # The control fills at the next open: shift the signal bar by one.
            nxt = {bars[i][0]: bars[i + 1][0] for i in range(len(bars) - 1)}
            assert [nxt[x["t"]] for x in out] == [x["t_in"] for x in ctl if x["reason"] != "OUVERTE"], (s, tf)
            table(f"{s} {tf}", out, base)

def direction(bars, buys_t, thresholds=(0.02, 0.03, 0.05), cap=300, every=5, start=T2024, warm=300):
    """Replica of the Pine verdict: from each start close, does +x come before -x? (cap bars,
    same bar touching both = down). Starts: BUY bars, and every `every`-th bar as the baseline."""
    t = [b[0] for b in bars]; h = [b[2] for b in bars]; l = [b[3] for b in bars]; c = [b[4] for b in bars]
    buy_set = set(buys_t); res = {True: [[0, 0] for _ in thresholds], False: [[0, 0] for _ in thresholds]}
    for i in range(warm, len(c)):
        if t[i] < start:
            continue
        for is_buy in ((True,) if t[i] in buy_set else ()) + ((False,) if i % every == 0 else ()):
            for k, x in enumerate(thresholds):
                for j in range(i + 1, min(len(c), i + cap + 1)):
                    if l[j] <= c[i] * (1 - x):
                        res[is_buy][k][1] += 1; break
                    if h[j] >= c[i] * (1 + x):
                        res[is_buy][k][0] += 1; res[is_buy][k][1] += 1; break
    return res
