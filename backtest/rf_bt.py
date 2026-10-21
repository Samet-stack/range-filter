"""Python replica of range-filter-spot-v4.pine (default inputs), bar-close decisions,
market fills at next open, protective stop simulated inside the bar.
Usage: python3 -I rf_bt.py [timeframe_label]   (reads data/<SYM>.csv)"""
import csv, math, sys, time
from pathlib import Path

DATA = Path(__file__).parent / "data"
T2024, T2026 = 1704067200000, 1767225600000  # 2024-01-01, 2026-01-01 UTC

def load(sym):
    with open(DATA / f"{sym}.csv") as f:
        r = list(csv.reader(f))[1:]
    return [(int(x[0]), *map(float, x[1:])) for x in r]

def ema(xs, n):  # Pine ta.ema: SMA seed over the first n non-na values
    out, a, buf, prev = [None] * len(xs), 2 / (n + 1), [], None
    for i, x in enumerate(xs):
        if x is None:
            continue
        if prev is None:
            buf.append(x)
            if len(buf) == n:
                prev = sum(buf) / n
                out[i] = prev
            continue
        prev = a * x + (1 - a) * prev
        out[i] = prev
    return out

def rma(xs, n):
    out, buf, prev = [None] * len(xs), [], None
    for i, x in enumerate(xs):
        if prev is None:
            buf.append(x)
            if len(buf) == n:
                prev = sum(buf) / n
                out[i] = prev
            continue
        prev = (x + (n - 1) * prev) / n
        out[i] = prev
    return out

def simulate(bars, period=100, mult=3.0, control=False, cost=0.10, start=T2024,
             atr_len=14, atr_floor=0.25, range_bars=20, er_len=20, stop_buf=0.25):
    t = [b[0] for b in bars]; o = [b[1] for b in bars]; h = [b[2] for b in bars]
    l = [b[3] for b in bars]; c = [b[4] for b in bars]; n = len(bars)
    raw = [None] + [abs(c[i] - c[i - 1]) for i in range(1, n)]
    second = ema(ema(raw, period), period * 2 - 1)
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, n)]
    atr = rma(tr, atr_len)
    warm = max(period * 3, er_len + 3, atr_len)
    rt = 2 * cost / 100
    c_side = cost / 100

    filt = None; flat_bars = 0; last_dir = 0; last_src = None
    pos = None  # dict(entry, stop, ebar)
    pending_entry = False; pending_exit = False  # False = no order, else stop level or None
    last_exit_bar = None
    trades = []; bars_in_window = 0; bars_in_pos = 0

    def close_trade(px, bar, reason):
        nonlocal pos, last_exit_bar
        ret = (px * (1 - c_side) - pos["entry"] * (1 + c_side)) / pos["entry"]
        trades.append(dict(t_in=t[pos["ebar"]], t_out=t[bar], ret=ret, reason=reason,
                           gross=px / pos["entry"] - 1, bars=bar - pos["ebar"]))
        pos = None

    for i in range(n):
        # --- intrabar: fills at open, then protective stop ---
        stop_hit_now = False
        if pending_exit and pos:
            close_trade(o[i], i, pending_exit); pending_exit = False
        if pending_entry is not False and pos is None:
            pos = dict(entry=o[i], stop=pending_entry, ebar=i)
            pending_entry = False
        if pos and pos["stop"] is not None:
            if o[i] <= pos["stop"]:
                close_trade(o[i], i, "STOP"); stop_hit_now = True
            elif l[i] <= pos["stop"]:
                close_trade(pos["stop"], i, "STOP"); stop_hit_now = True
        if stop_hit_now:
            last_exit_bar = i

        # --- engine at close ---
        width = None
        if second[i] is not None and atr[i] is not None:
            width = max(second[i] * mult, max(1e-12, atr[i] * atr_floor))
        ready = i >= 1 and width is not None and i >= warm
        step = 0; prev_f = None
        if not ready:
            filt = None; flat_bars = 0; last_dir = 0; last_src = None
        else:
            prev_f = c[i] if filt is None else filt
            cand = max(prev_f, c[i] - width) if c[i] > prev_f else min(prev_f, c[i] + width)
            supports = (c[i] > c[i - 1]) if cand > prev_f else (c[i] < c[i - 1]) if cand < prev_f else True
            filt = cand if supports else prev_f
            step = 1 if filt > prev_f else -1 if filt < prev_f else 0
            if step != 0 and step == last_dir:
                if not (c[i] > last_src if step == 1 else c[i] < last_src):
                    filt = prev_f; step = 0
            if step != 0:
                last_dir = step; last_src = c[i]
            flat_bars = flat_bars + 1 if step == 0 else 0

        in_window = t[i] >= start
        if in_window and ready:
            bars_in_window += 1
            if pos:
                bars_in_pos += 1

        if pos:
            long_flat = flat_bars >= range_bars
            net_gain = c[i] > pos["entry"] * (1 + rt)
            reason = None
            if step == -1:
                reason = "INVALIDATION"
            elif long_flat and (control or not net_gain):
                reason = "STAGNATION"
            if reason:
                pending_exit = reason; last_exit_bar = i
        elif ready and in_window and step == 1 and i + 1 < n:
            if last_exit_bar is not None and i <= last_exit_bar:
                continue  # no buy on the bar of an exit
            stop = None if control else filt - width - stop_buf * atr[i]
            pending_entry = stop
    if pos:  # mark open position at last close
        close_trade(c[-1], n - 1, "OUVERTE")
    return trades, (bars_in_pos / bars_in_window if bars_in_window else 0)

def stats(tr):
    k = len(tr)
    if k == 0:
        return dict(n=0)
    r = [x["ret"] * 100 for x in tr]
    m = sum(r) / k
    sd = math.sqrt(sum((x - m) ** 2 for x in r) / (k - 1)) if k > 1 else 0
    eq = pk = dd = 0
    for x in r:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    wins = [x for x in r if x > 0]; loss = [x for x in r if x <= 0]
    return dict(n=k, mean=m, t=m / (sd / math.sqrt(k)) if sd > 0 else float("nan"),
                tot=sum(r), win=100 * len(wins) / k,
                pf=sum(wins) / -sum(loss) if loss and sum(loss) < 0 else float("inf"),
                dd=dd, gross=100 * sum(x["gross"] for x in tr) / k)

def bh(bars, t0, t1, cost):
    sel = [b for b in bars if t0 <= b[0] < t1]
    if not sel:
        return None, None
    p0 = sel[0][1]; pk = p0; dd = 0
    for b in sel:
        pk = max(pk, b[2]); dd = max(dd, 1 - b[3] / pk)
    return 100 * (sel[-1][4] / p0 - 1 - 2 * cost / 100), 100 * dd
