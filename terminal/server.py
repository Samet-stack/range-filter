"""Local trading terminal: live candles (Hyperliquid spot by default; or Hyperliquid perp; or Binance, else Bybit, else Hyperliquid), Range Filter signals,
daily trend switch, simple probable range, optional Kronos paths. Reads public market data only:
no account, no key, no order.
Run: ~/kronos/.venv/bin/python -I ~/range-filter/terminal/server.py   then open http://localhost:7071"""
import json, sys, threading, time, urllib.request
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine

MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
HIST = 1500  # candles kept per chart (filter warm-up is 300)
app = Flask(__name__, static_folder=str(HERE / "static"))
lock = threading.Lock()
gpu = threading.Lock()  # Kronos runs one batch at a time, without blocking the candle cache
cache = {}   # (sym, tf) -> dict(rows, src, full_at, tick_at)


def get(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "rf-terminal"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def binance(sym, tf, n):
    rows, end = [], None
    while len(rows) < n:
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval={tf}&limit={min(1000, n - len(rows))}"
        k = get(url + (f"&endTime={end}" if end else ""))
        if not k:
            break
        rows = [(r[0], *map(float, r[1:5])) for r in k] + rows
        end = k[0][0] - 1
        if len(k) < 1000:
            break
    return rows


def bybit(sym, tf, n):
    iv = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}[tf]
    rows, end = {}, None
    while len(rows) < n:
        url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}USDT&interval={iv}&limit={min(1000, n - len(rows))}"
        k = get(url + (f"&end={end}" if end else ""))["result"]["list"]
        if not k:
            break
        for r in k:
            rows[int(r[0])] = (int(r[0]), *map(float, r[1:5]))
        end = min(int(r[0]) for r in k) - 1
        if len(k) < 1000:
            break
    return sorted(rows.values())


def hyperliquid(sym, tf, n):
    now = int(time.time() * 1000)
    k = get("https://api.hyperliquid.xyz/info", {"type": "candleSnapshot", "req": {
        "coin": sym, "interval": tf, "startTime": now - (n + 2) * MS[tf], "endTime": now}})
    return [(int(r["t"]), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])) for r in k]


spot_meta = {"at": 0, "names": {}}


def hl_spot_coin(sym):
    """Hyperliquid spot market id for a token against USDC: SYM or its bridged name USYM (UETH, UBTC...)."""
    if time.time() - spot_meta["at"] > 3600:
        d = get("https://api.hyperliquid.xyz/info", {"type": "spotMeta"})
        tok = {t["index"]: t["name"] for t in d["tokens"]}
        spot_meta["names"] = {tok[u["tokens"][0]].upper(): (u["name"], f"{tok[u['tokens'][0]]}/USDC")
                              for u in d["universe"] if tok[u["tokens"][1]] == "USDC"}
        spot_meta["at"] = time.time()
    names = spot_meta["names"]
    return names.get(sym.upper()) or names.get("U" + sym.upper())


def hl_coin(coin):
    return lambda sym, tf, n: hyperliquid(coin, tf, n)


def fetchers(sym, source):
    """Candidate (label, fetch) pairs in order of preference."""
    auto = [("Binance", lambda s, tf, n: binance(s.upper(), tf, n)), ("Bybit", lambda s, tf, n: bybit(s.upper(), tf, n)),
            ("Hyperliquid perp", hl_coin(sym))]
    if source == "auto":
        return auto
    perp = [("Hyperliquid perp", hl_coin(sym))]
    if source == "hl_perp":
        return perp
    try:
        m = hl_spot_coin(sym)
    except Exception:
        m = None
    spot = [(f"Hyperliquid spot {m[1]}", hl_coin(m[0]))] if m else []
    return spot + [("Hyperliquid perp (pas de spot)", hl_coin(sym))]


def candles(sym, tf, n=HIST, source="hl_spot"):
    """Cached history; the last candles are refreshed every few seconds."""
    key, now = (sym, tf, source), time.time()
    with lock:
        c = cache.get(key)
    if c and now - c["tick_at"] < 3:
        return c
    if c and now - c["full_at"] < 600:
        try:
            new = c["fn"](sym, tf, 3)
            rows = {r[0]: r for r in c["rows"]}
            rows.update({r[0]: r for r in new})
            c = dict(c, rows=sorted(rows.values())[-n:], tick_at=now)
        except Exception:
            c = dict(c, tick_at=now)
    else:
        c = None
        for src, f in fetchers(sym, source):
            try:
                rows = f(sym, tf, n)
            except Exception:
                continue
            if len(rows) >= 100:
                c = dict(rows=rows[-n:], src=src, fn=f, full_at=now, tick_at=now); break
        if c is None:
            raise LookupError(f"{sym} introuvable ({'Hyperliquid' if source != 'auto' else 'Binance, Bybit, Hyperliquid'})")
    with lock:
        cache[key] = c
    return c


def split(rows, tf):
    now = int(time.time() * 1000)
    if rows and rows[-1][0] + MS[tf] > now:
        return rows[:-1], rows[-1]
    return rows, None


def analyse(sym, tf, source):
    c = candles(sym, tf, source=source)
    closed, live = split(c["rows"], tf)
    rf = engine.range_filter(closed, live)
    try:
        dclosed, _ = split(candles(sym, "1d", 120, source)["rows"], "1d")
        reg = engine.regime([r[4] for r in dclosed])
    except Exception:
        reg = dict(up=None, close=None, sma=None)
    code, word, detail = engine.state(rf, reg)
    price = rf["price"]
    rng = engine.simple_range(closed, price)
    return c, closed, live, rf, reg, code, word, detail, rng


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/watch")
def watch():
    tf, source = request.args.get("tf", "1h"), request.args.get("src", "hl_spot")
    out = []
    for sym in [s.strip() for s in request.args.get("syms", "").split(",") if s.strip()][:30]:
        try:
            c, closed, live, rf, reg, code, word, detail, rng = analyse(sym, tf, source)
            rows = c["rows"]; t_now = rows[-1][0]
            day_ago = next((r[4] for r in reversed(rows) if r[0] <= t_now - 86_400_000), None)
            out.append(dict(sym=sym, price=rf["price"], chg24=(rf["price"] / day_ago - 1) if day_ago else None,
                            code=code, word=word, regime=reg["up"], src=c["src"],
                            width=(rng["top"] - rng["bot"]) / rf["price"] if rng else None))
        except Exception as e:
            out.append(dict(sym=sym, error=str(e)))
    return jsonify(out)


@app.get("/api/chart")
def chart():
    sym, tf, source = request.args["sym"], request.args.get("tf", "1h"), request.args.get("src", "hl_spot")
    try:
        c, closed, live, rf, reg, code, word, detail, rng = analyse(sym, tf, source)
    except Exception as e:
        return jsonify(error=str(e)), 404
    show = 500
    rows = c["rows"][-show:]
    first_t = rows[0][0]
    off = len(closed) - (len(rows) - (1 if live else 0))
    filt = [dict(time=closed[off + i][0] // 1000, value=v, dir=d)
            for i, (v, d) in enumerate(zip(rf["filt"][off:], rf["dir"][off:])) if v is not None]
    ev = [dict(e, time=e["t"] // 1000) for e in rf["events"] if e["t"] >= first_t]
    t_form = live[0] if live else closed[-1][0] + MS[tf]
    return jsonify(
        sym=sym, tf=tf, src=c["src"],
        candles=[dict(time=r[0] // 1000, open=r[1], high=r[2], low=r[3], close=r[4]) for r in rows],
        filt=filt, events=ev, code=code, word=word, detail=detail, price=rf["price"],
        in_move=rf["in_move"], ref=rf["ref"], mfe=rf["mfe"], mae=rf["mae"], since_buy=rf["since_buy"],
        buy_level=rf["buy_level"], fin_level=rf["fin_level"], fdir=rf["fdir"],
        close_at=t_form + MS[tf], live=live is not None,
        regime=reg, range=dict(rng, t0=t_form // 1000, t1=(t_form + (rng["hz"] - 1) * MS[tf]) // 1000) if rng else None)


kronos = {"pred": None, "cache": {}}


@app.get("/api/kronos")
def kronos_paths():
    sym, tf, source = request.args["sym"], request.args.get("tf", "1h"), request.args.get("src", "hl_spot")
    paths_n, hz = 50, 24
    c = candles(sym, tf, source=source)
    closed, live = split(c["rows"], tf)
    key = (sym, tf, c["src"], closed[-1][0])
    if key in kronos["cache"]:
        return jsonify(kronos["cache"][key])
    sys.path.insert(0, str(Path.home() / "kronos"))
    import pandas as pd, torch
    from model import Kronos, KronosTokenizer, KronosPredictor
    if kronos["pred"] is None:
        kronos["pred"] = KronosPredictor(Kronos.from_pretrained("NeoQuasar/Kronos-small"),
                                         KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base"),
                                         device="cuda:0" if torch.cuda.is_available() else "cpu", max_context=512)
    ctx = closed[-400:]
    df = pd.DataFrame([r[1:5] for r in ctx], columns=["open", "high", "low", "close"])
    xts = pd.Series(pd.to_datetime([r[0] for r in ctx], unit="ms"))
    t0 = ctx[-1][0]
    fut = [t0 + MS[tf] * i for i in range(1, hz + 1)]
    yts = pd.Series(pd.to_datetime(fut, unit="ms"))
    with gpu:
        ps = kronos["pred"].predict_batch([df] * paths_n, [xts] * paths_n, [yts] * paths_n, pred_len=hz,
                                          T=1.0, top_p=0.9, sample_count=1, verbose=False)
    last = ctx[-1][4]
    out = dict(start=dict(time=t0 // 1000, value=last), times=[t // 1000 for t in fut],
               paths=[p["close"].round(10).tolist() for p in ps])
    kronos["cache"][key] = out
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7071, debug=False, threaded=True)
