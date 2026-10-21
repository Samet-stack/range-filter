"""Clean directional test: from the BUY close, which comes first, +x% or -x%? (no FIN stop,
cap 300 bars; same bar touching both counts as down, conservative). Baseline: random closes."""
import sys, math, random
sys.path.insert(0, ".")
from pathlib import Path
import rf_bt
from indicator_stats import moves
random.seed(3)
CAP = 300
def first_hit(h, l, c, i0, x):
    r = c[i0]
    for k in range(i0 + 1, min(len(c), i0 + CAP + 1)):
        if l[k] <= r * (1 - x): return 0
        if h[k] >= r * (1 + x): return 1
    return None
for x in (0.02, 0.03, 0.04):
    print(f"\n=== +{x:.0%} avant -{x:.0%} ===")
    for tf, d in (("1h", "data1h"), ("4h", "data")):
        rf_bt.DATA = Path(d)
        for s in ("BTC", "ETH", "ZEC", "HYPE"):
            bars = rf_bt.load(s); t=[b[0] for b in bars]; h=[b[2] for b in bars]; l=[b[3] for b in bars]; c=[b[4] for b in bars]
            idx = {v: i for i, v in enumerate(t)}
            out, _ = moves(bars)
            buy = [r for r in (first_hit(h, l, c, idx[m["t"]], x) for m in out) if r is not None]
            rnd = [r for r in (first_hit(h, l, c, random.randint(300, len(c) - 2), x) for _ in range(20 * len(out))) if r is not None]
            p1 = sum(buy) / len(buy); p0 = sum(rnd) / len(rnd)
            z = (p1 - p0) / math.sqrt(p0 * (1 - p0) / len(buy) + p0 * (1 - p0) / len(rnd))
            print(f"{s:4s} {tf}: BUY {100*p1:3.0f}% (n={len(buy):3d})  hasard {100*p0:3.0f}%  z={z:+4.1f}")
