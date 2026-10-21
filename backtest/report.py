import sys, time
sys.path.insert(0, __import__("os").path.dirname(__file__))
from rf_bt import *

NOW = int(time.time() * 1000)
PER = [("dev 2024-25", T2024, T2026), ("OOS 2026", T2026, NOW)]
SYMS = ["BTC", "ETH", "ZEC", "HYPE"]
data = {s: load(s) for s in SYMS}

def fmt(s):
    if s["n"] == 0:
        return "   0 trades"
    return f"{s['n']:4d} tr  brut {s['gross']:+6.2f}%  net {s['mean']:+6.2f}%/tr (t={s['t']:+4.1f})  win {s['win']:3.0f}%  PF {s['pf']:4.2f}  somme {s['tot']:+7.1f}%  DD {s['dd']:5.1f}%"

for cost in (0.10, 0.27):
    print(f"\n===== 4h, cout {cost:.2f}%/cote =====")
    for s in SYMS:
        for ver, ctl in (("Temoin ", True), ("Ameliore", False)):
            tr, expo = simulate(data[s], control=ctl, cost=cost)
            for name, a, b in PER:
                st = stats([x for x in tr if a <= x["t_in"] < b])
                print(f"{s:4s} {ver} {name:11s} {fmt(st)}  expo {100*expo:3.0f}%")
        for name, a, b in PER:
            r, dd = bh(data[s], max(a, data[s][300][0]), b, cost)
            print(f"{s:4s} ACHAT-CONS {name:11s} {r:+8.1f}%  DD {dd:5.1f}%")
        print()

print("\n===== Sensibilite (Ameliore, 0.10%, OOS 2026 : esperance %/trade par actif) =====")
for p in (70, 100, 140):
    for m in (2.5, 3.0, 3.5):
        row = []
        for s in SYMS:
            tr, _ = simulate(data[s], period=p, mult=m)
            st = stats([x for x in tr if x["t_in"] >= T2026])
            row.append(f"{s} {st.get('mean', float('nan')):+5.2f} (n={st['n']:2d})")
        print(f"P={p:3d} m={m}: " + "  ".join(row))
