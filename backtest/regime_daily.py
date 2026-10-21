"""Spot risk switch test: daily close > SMA(n) vs buy & hold (return, worst drawdown). Usage: python3 -I regime_daily.py"""
# Daily trend switch for spot: hold when the daily close > SMA(n) of daily closes (decided at the daily close,
# act at that close), 0.20% round trip. Also the Range Filter on daily bars. Vs buy & hold.
import sys; sys.path.insert(0, '/home/9lx7/range-filter/backtest')
import rf_bt
from pathlib import Path
from indicator_stats import moves
rf_bt.DATA = Path('/home/9lx7/range-filter/backtest/data')
def mdd(eq):
    pk, m = eq[0], 0.0
    for v in eq: pk = max(pk, v); m = min(m, v / pk - 1)
    return m
def run(c, pos, i0):
    e, eq = 1.0, [1.0]
    for i in range(i0 + 1, len(c)):
        e *= 1 + (c[i] / c[i - 1] - 1) * pos[i - 1]
        if pos[i] != pos[i - 1]: e *= 0.999
        eq.append(e)
    return eq
for start, lab in ((1704067200000, "2024+"), (1767225600000, "2026 ")):
    for s in ("BTC", "ETH", "ZEC", "HYPE"):
        b4 = rf_bt.load(s); D = {}
        for t, o, h, l, c in b4:
            d = t // 86400000 * 86400000
            if d not in D: D[d] = [d, o, h, l, c]
            else: D[d][2] = max(D[d][2], h); D[d][3] = min(D[d][3], l); D[d][4] = c
        days = [tuple(v) for v in sorted(D.values())][:-1]
        t = [d[0] for d in days]; c = [d[4] for d in days]
        i0 = next(i for i in range(len(t)) if t[i] >= start)
        bh = [c[i] / c[i0] for i in range(i0, len(c))]
        line = f"{lab} {s:4} | buy&hold {100*(bh[-1]-1):+6.0f}% chute {100*mdd(bh):4.0f}%"
        for n in (20, 50):
            pos = [0] * len(c)
            for i in range(n, len(c)): pos[i] = 1 if c[i] > sum(c[i - n + 1:i + 1]) / n else 0
            eq = run(c, pos, i0)
            line += f" | SMA{n} {100*(eq[-1]-1):+6.0f}% chute {100*mdd(eq):4.0f}% ({100*sum(pos[i0:])/(len(c)-i0):.0f}% investi)"
        print(line)
