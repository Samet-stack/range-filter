"""Does the signal's timing beat random entries with the same holding durations?
p = share of random runs whose summed net return >= the strategy's."""
import random, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rf_bt import *
random.seed(0)
NOW = int(time.time() * 1000)
for ctl, ver in ((True, "Temoin"), (False, "Ameliore")):
    for s in ("BTC", "ETH", "ZEC", "HYPE"):
        bars = load(s); ts = [b[0] for b in bars]; o = [b[1] for b in bars]
        tr, _ = simulate(bars, control=ctl)
        for name, a, b in (("dev", T2024, T2026), ("OOS", T2026, NOW)):
            sel = [x for x in tr if a <= x["t_in"] < b]
            if len(sel) < 5:
                continue
            real = sum(x["ret"] for x in sel)
            idx = [i for i, t in enumerate(ts) if max(a, ts[300]) <= t < b]
            lo, hi = idx[0], idx[-1]
            beat = 0; R = 2000; sims = []
            for _ in range(R):
                tot = 0
                for x in sel:
                    d = max(1, x["bars"])
                    i = random.randint(lo, max(lo, hi - d))
                    tot += o[i + d] * 0.999 / (o[i] * 1.001) - 1
                sims.append(tot); beat += tot >= real
            sims.sort()
            print(f"{ver:8s} {s:4s} {name}: strat {100*real:+7.1f}%  hasard median {100*sims[R//2]:+7.1f}%  p={beat/R:.2f}")
