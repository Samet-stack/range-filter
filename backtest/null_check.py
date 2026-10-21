"""Calibration of the Pine verdict on pure random walks: z should be ~N(0,1) and
'AVANTAGE' (z >= 2) should fire rarely (~2-3 %)."""
import sys, math, random
sys.path.insert(0, ".")
from indicator_stats import moves, direction
random.seed(7)
zs = []
for run in range(30):
    bars, p, t = [], 100.0, 0
    for i in range(12000):  # 1h-like: 4 sub-steps per bar, ~0.7 % per bar
        o = p; hi = lo = p
        for _ in range(4):
            p *= math.exp(random.gauss(0, 0.0035)); hi = max(hi, p); lo = min(lo, p)
        bars.append((t, o, hi, lo, p)); t += 3600000
    out, _ = moves(bars, samples=0, start=0)
    r = direction(bars, [m["t"] for m in out], start=0)
    (u1, n1), (u0, n0) = r[True][1], r[False][1]
    p1, p0 = u1 / n1, u0 / n0
    zs.append((p1 - p0) / math.sqrt(p0 * (1 - p0) * (1 / n1 + 1 / n0)))
m = sum(zs) / len(zs); sd = math.sqrt(sum((z - m) ** 2 for z in zs) / (len(zs) - 1))
print(f"30 marches aleatoires : z moyen {m:+.2f}, ecart-type {sd:.2f}, AVANTAGE (z>=2) {sum(z>=2 for z in zs)}/30, 'leger mieux' (1<=z<2) {sum(1<=z<2 for z in zs)}/30")
