"""Download 4h spot candles: Binance (BTC, ETH, ZEC) and Bybit (HYPE). Output CSV: t,o,h,l,c."""
import csv, json, sys, time, urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "data"
START = 1690848000000  # 2023-08-01 UTC, warmup before 2024-01
H4 = 4 * 3600 * 1000

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)

def binance(sym):
    rows, t = [], START
    while True:
        k = get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=4h&startTime={t}&limit=1000")
        if not k:
            break
        rows += [(r[0], *map(float, r[1:5])) for r in k]
        t = k[-1][0] + H4
        if len(k) < 1000:
            break
    return rows

def bybit(sym):
    rows, end = {}, int(time.time() * 1000)
    while True:
        k = get(f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}&interval=240&end={end}&limit=1000")["result"]["list"]
        if not k:
            break
        for r in k:
            rows[int(r[0])] = (int(r[0]), *map(float, r[1:5]))
        oldest = min(int(r[0]) for r in k)
        if len(k) < 1000 or oldest <= START:
            break
        end = oldest - 1
    return sorted(rows.values())

def save(name, rows):
    now = int(time.time() * 1000)
    rows = [r for r in rows if r[0] + H4 <= now]  # closed candles only
    with open(OUT / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow("tohlc"); w.writerows(rows)
    print(name, len(rows), time.strftime("%Y-%m-%d", time.gmtime(rows[0][0] / 1000)), "->", time.strftime("%Y-%m-%d", time.gmtime(rows[-1][0] / 1000)))

for s in ("BTCUSDT", "ETHUSDT", "ZECUSDT"):
    save(s[:-4], binance(s))
save("HYPE", bybit("HYPEUSDT"))
