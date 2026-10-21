"""Manual-use question: after a BUY (V3.1 control signal, filled at next open),
how often does the high reach +X% before the V4 sale, how deep is the dip first,
and what does 'close at +X% or else at the V4 sale' net? Baseline: random entries
with the same holding durations and the same rule."""
import random, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rf_bt
from rf_bt import simulate, T2024, T2026
from pathlib import Path
random.seed(1)
COST = 0.001  # 0.10 % per side
NOW = int(time.time() * 1000)

def run_rule(h, l, o, c, i0, i1, tgt):
    """Enter at o[i0]; exit at +tgt if high touches it before bar i1 (sale fill bar), else at o[i1]."""
    e = o[i0]; mae = 0.0
    for k in range(i0, i1):
        if h[k] >= e * (1 + tgt):
            px = e * (1 + tgt); return True, mae, px * (1 - COST) / (e * (1 + COST)) - 1
        mae = min(mae, l[k] / e - 1)
    px = o[i1] if i1 < len(o) else c[-1]
    return False, mae, px * (1 - COST) / (e * (1 + COST)) - 1

for tf, d in (("1h", "data1h"), ("4h", "data")):
    rf_bt.DATA = Path(__file__).parent / d
    print(f"\n===== {tf} : 'fermer a +X % sinon a la vente V4', couts 0,10 %/cote =====")
    for s in ("BTC", "ETH", "ZEC", "HYPE"):
        bars = rf_bt.load(s); t = [b[0] for b in bars]
        o = [b[1] for b in bars]; h = [b[2] for b in bars]; l = [b[3] for b in bars]; c = [b[4] for b in bars]
        idx = {x: i for i, x in enumerate(t)}
        tr, _ = simulate(bars, control=True)
        for per, a, b in (("2024-25", T2024, T2026), ("2026", T2026, NOW)):
            sel = [x for x in tr if a <= x["t_in"] < b]
            if len(sel) < 10:
                continue
            lo = max(idx[sel[0]["t_in"]] - 50, 300); hi = max(i for i, x in enumerate(t) if x < b)
            out = []
            for tgt in (0.03, 0.04):
                res = [run_rule(h, l, o, c, idx[x["t_in"]], idx[x["t_in"]] + max(1, x["bars"]), tgt) for x in sel]
                hit = sum(r[0] for r in res) / len(res)
                maes = sorted(r[1] for r in res if r[0])
                net = 100 * sum(r[2] for r in res) / len(res)
                # random baseline, 1000 draws of the same trade set
                rnd_hit = rnd_net = 0; R = 300
                for _ in range(R):
                    rr = []
                    for x in sel:
                        dd = max(1, x["bars"]); i = random.randint(lo, max(lo, hi - dd))
                        rr.append(run_rule(h, l, o, c, i, i + dd, tgt))
                    rnd_hit += sum(r[0] for r in rr) / len(rr); rnd_net += 100 * sum(r[2] for r in rr) / len(rr)
                med_mae = 100 * maes[len(maes) // 2] if maes else float("nan")
                out.append(f"+{int(tgt*100)}%: touche {100*hit:3.0f}% (hasard {100*rnd_hit/R:3.0f}%) baisse avant {med_mae:+5.1f}%  net {net:+5.2f}%/tr (hasard {rnd_net/R:+5.2f})")
            print(f"{s:4s} {per:7s} n={len(sel):3d} | " + " | ".join(out))
