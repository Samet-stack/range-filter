"""Fixed Kronos: widen its range by factors learned on the first half of each series (2026 H1),
judged on the second half. Compared with the simple method (also recalibrated the same way) and
with a blend of both. Reads kronos_range.csv from kronos_range_test.py.
Usage: ~/kronos/.venv/bin/python -I kronos_fix_test.py"""
import numpy as np, pandas as pd
from pathlib import Path
R = pd.read_csv(Path(__file__).parent / "kronos_range.csv")
R["half"] = R.groupby(["tf", "sym"]).cumcount() / R.groupby(["tf", "sym"]).sym.transform("size") >= 0.5
def pin(y, q, tau):
    d = y - q; return np.mean(np.maximum(tau * d, (tau - 1) * d))
def fit(y, q, tau):  # scale s so that the share of y beyond s*q matches 1-tau (top) / tau (bottom)
    best = min(np.linspace(0.3, 4, 371), key=lambda s: pin(y, s * q, tau)); return best
print("Correction apprise sur janv-mai 2026, jugee sur juin-oct 2026. Ideal : 10 % / 10 %. Erreur : plus bas = mieux.")
for tf in ("4h", "1h"):
    A, B = R[(R.tf == tf) & ~R.half].copy(), R[(R.tf == tf) & R.half].copy()
    for lab, top, bot in (("Kronos brut    ", "k_top", "k_bot"), ("Kronos corrige ", "k_top", "k_bot"),
                          ("Methode simple ", "s_top", "s_bot"), ("Melange des 2  ", "m_top", "m_bot")):
        for D in (A, B):
            D["m_top"] = (D.k_top * fit(A.r_top, A.k_top, .9) + D.s_top * fit(A.r_top, A.s_top, .9)) / 2
            D["m_bot"] = (D.k_bot * fit(A.r_bot, A.k_bot, .1) + D.s_bot * fit(A.r_bot, A.s_bot, .1)) / 2
        a = 1.0 if lab.startswith("Kronos brut") else fit(A.r_top, A[top], .9)
        b = 1.0 if lab.startswith("Kronos brut") else fit(A.r_bot, A[bot], .1)
        qt, qb = B[top] * a, B[bot] * b
        print(f"{tf} {lab} | casse le haut {100 * (B.r_top > qt).mean():4.1f} %  casse le bas {100 * (B.r_bot < qb).mean():4.1f} %"
              f"  | erreur {1e4 * (pin(B.r_top, qt, .9) + pin(B.r_bot, qb, .1)):6.1f}  (x{a:.2f} haut, x{b:.2f} bas, n={len(B)})")
