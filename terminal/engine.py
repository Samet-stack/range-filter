"""Terminal engine: Range Filter (same rules as range-filter-manuel.pine), daily trend switch,
simple probable range. Pure functions over candle lists; the forming candle is passed apart.
Range Filter replica validated against backtest/indicator_stats.py (same BUY/FIN)."""
import math
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))
from rf_bt import ema, rma  # Pine-exact ta.ema (SMA seed) and ta.rma

DEFAULTS = dict(period=100, mult=3.0, atr_len=14, atr_floor=0.25, range_bars=20,
                late_max=0.015, fee_rt=0.002, regime_len=50, range_h=12)


def range_filter(bars, live=None, p=DEFAULTS):
    """bars: closed candles [(t, o, h, l, c)], oldest first. live: forming candle or None.
    Returns per-bar filter values/directions, BUY/FIN events and the live state."""
    allb = bars + ([live] if live else [])
    h = [b[2] for b in allb]; l = [b[3] for b in allb]; c = [b[4] for b in allb]; n = len(allb)
    raw = [None] + [abs(c[i] - c[i - 1]) for i in range(1, n)]
    second = ema(ema(raw, p["period"]), p["period"] * 2 - 1)
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, n)]
    atr = rma(tr, p["atr_len"])
    warm = max(p["period"] * 3, p["atr_len"])
    width = [max(second[i] * p["mult"], atr[i] * p["atr_floor"]) if second[i] is not None and atr[i] is not None else None
             for i in range(n)]
    filt = None; fdir = 0; flat = 0; last_dir = 0; last_src = None
    in_move = False; ref = None; b0 = None; mfe = mae = 0.0
    out_f, out_d, events = [], [], []
    for i in range(len(bars)):
        step = 0
        ready = i >= 1 and width[i] is not None and i >= warm
        if not ready:
            filt = None; fdir = 0; flat = 0; last_dir = 0; last_src = None
        else:
            pf = c[i] if filt is None else filt
            w = width[i]
            cand = max(pf, c[i] - w) if c[i] > pf else min(pf, c[i] + w)
            sup = (c[i] > c[i - 1]) if cand > pf else (c[i] < c[i - 1]) if cand < pf else True
            filt = cand if sup else pf
            step = 1 if filt > pf else -1 if filt < pf else 0
            if step and step == last_dir and not (c[i] > last_src if step == 1 else c[i] < last_src):
                filt = pf; step = 0
            if step:
                last_dir = step; last_src = c[i]
            flat = flat + 1 if step == 0 else 0
            if step:
                fdir = step
            elif flat >= p["range_bars"]:
                fdir = 0
        if in_move:
            mfe = max(mfe, h[i] / ref - 1); mae = min(mae, l[i] / ref - 1)
            if step == -1 or flat >= p["range_bars"]:
                in_move = False
                events.append(dict(kind="FIN", i=i, t=allb[i][0], price=c[i], res=c[i] / ref - 1 - p["fee_rt"],
                                   mfe=mfe, reason="inversion" if step == -1 else "plat prolonge"))
        elif ready and step == 1:
            in_move = True; ref = c[i]; b0 = i; mfe = mae = 0.0
            events.append(dict(kind="BUY", i=i, t=allb[i][0], price=c[i]))
        out_f.append(filt); out_d.append(fdir)

    # Close levels for the bar being judged (forming bar if any): exact engine step conditions.
    k = len(bars) if live else len(bars) - 1
    prev_close = c[k - 1] if live else c[k]
    w_now = width[k] if k < n else None
    ready_now = w_now is not None and k >= warm and filt is not None
    buy_level = fin_level = None
    if ready_now:
        buy_level = max(filt + w_now, prev_close, last_src if last_dir == 1 else prev_close)
        fin_level = min(filt - w_now, prev_close, last_src if last_dir == -1 else prev_close)
    price = c[-1]
    return dict(filt=out_f, dir=out_d, events=events, ready=ready_now, in_move=in_move, ref=ref,
                buy_t=allb[b0][0] if in_move else None, since_buy=(k - b0) if in_move else None,
                mfe=max(mfe, h[-1] / ref - 1) if in_move else None, mae=min(mae, l[-1] / ref - 1) if in_move else None,
                buy_level=buy_level, fin_level=fin_level, flat=flat, fdir=fdir, price=price,
                preview_buy=bool(live and ready_now and not in_move and price > buy_level),
                preview_fin=bool(live and ready_now and in_move and (price < fin_level or (flat + 1 >= p["range_bars"] and price <= buy_level))))


def regime(daily_closes, n=DEFAULTS["regime_len"]):
    """Closed daily closes, oldest first. Up when the last close is above its n-day SMA."""
    if len(daily_closes) < n:
        return dict(up=None, close=None, sma=None)
    sma = sum(daily_closes[-n:]) / n
    return dict(up=daily_closes[-1] > sma, close=daily_closes[-1], sma=sma)


def simple_range(bars, anchor, hz=DEFAULTS["range_h"], nv=48):
    """Probable high/low over the next hz bars: past windows' max-high / min-low moves, each scaled by
    its volatility at the time, 90th / 10th percentile, rescaled by the current volatility.
    Tested on 2026 (backtest/kronos_range_test.py): broken about 1 time in 10 on each side."""
    h = np.array([b[2] for b in bars]); l = np.array([b[3] for b in bars]); c = np.array([b[4] for b in bars])
    if len(c) < nv + hz + 50:
        return None
    lr = np.diff(np.log(c))
    up, dn = [], []
    for i in range(nv, len(c) - hz):
        v = lr[i - nv:i].std()
        if v > 0:
            up.append((h[i + 1:i + hz + 1].max() / c[i] - 1) / v); dn.append((l[i + 1:i + hz + 1].min() / c[i] - 1) / v)
    v_now = lr[-nv:].std()
    top = anchor * (1 + np.percentile(up, 90) * v_now); bot = anchor * (1 + np.percentile(dn, 10) * v_now)
    return dict(top=float(top), bot=float(bot), hz=hz)


def state(rf, reg, p=DEFAULTS):
    """Same priorities as the Pine indicator. Returns (code, word, detail)."""
    blocked = reg.get("up") is False
    if not rf["ready"]:
        return "INIT", "INITIALISATION", "historique trop court"
    from_buy = rf["price"] / rf["ref"] - 1 if rf["in_move"] else None
    window_raw = rf["in_move"] and from_buy <= p["late_max"]
    f = lambda x: f"{x:.6g}"
    pc = lambda x: f"{100 * x:+.1f} %"
    if rf["preview_fin"]:
        lv = rf["fin_level"]
        return "FIN_FORMING", "FIN ?", f"FIN si cloture < {f(lv)} ({pc(lv / rf['price'] - 1)})"
    if blocked and (window_raw or not rf["in_move"]):
        return "REGIME", "FOND BAISSIER", f"jour {f(reg['close'])} < moyenne 50 j {f(reg['sma'])} : pas d'achat spot"
    if window_raw:
        return "BUY", "ACHAT", f"BUY {f(rf['ref'])} il y a {rf['since_buy']} b. | prix {pc(from_buy)}"
    if rf["in_move"]:
        lv = rf["fin_level"]
        return "IN", f"EN COURS {pc(from_buy)}", f"deja {pc(from_buy)} depuis le BUY : trop tard | FIN si cloture < {f(lv)}"
    lv = rf["buy_level"]
    if rf["preview_buy"]:
        return "BUY_FORMING", "ACHAT ?", f"pas confirme : BUY si cloture > {f(lv)} ({pc(lv / rf['price'] - 1)})"
    if rf["fdir"] == -1:
        return "DOWN", "PAS D'ACHAT", f"BUY si cloture > {f(lv)} ({pc(lv / rf['price'] - 1)})"
    return "WAIT", "ATTENTE", f"BUY si cloture > {f(lv)} ({pc(lv / rf['price'] - 1)})"
