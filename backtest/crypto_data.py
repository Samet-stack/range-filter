"""Public OHLCV history for the isolated Kronos V2 experiment; original CSVs stay intact."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data_ohlcv"
COLUMNS = ["timestamps", "open", "high", "low", "close", "volume", "amount"]
SYMBOLS = ("BTC", "ETH", "HYPE", "ZEC")


def get_json(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                result = json.load(response)
            if isinstance(result, dict) and result.get("retCode") in (10000, 10006, 10016):
                raise OSError(f"Bybit temporairement indisponible : {result.get('retMsg')}")
            return result
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def validate_frame(df):
    if df.empty or df.timestamps.duplicated().any() or not df.timestamps.is_monotonic_increasing:
        raise ValueError("Historique vide, dupliqué ou non trié.")
    values = df[COLUMNS[1:]].to_numpy()
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4:] < 0).any():
        raise ValueError("Prix ou volumes invalides.")
    if ((df.high < df[["open", "close", "low"]].max(axis=1)) |
            (df.low > df[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Bougies OHLC incohérentes.")


def download(symbol, start, end):
    rows = {}
    if symbol == "HYPE":
        cursor = end - 1
        while cursor >= start:
            q = urllib.parse.urlencode(dict(category="spot", symbol="HYPEUSDT", interval="60", limit=1000, end=cursor))
            result = get_json("https://api.bybit.com/v5/market/kline?" + q)
            if result.get("retCode") != 0:
                raise ValueError(f"Bybit: {result.get('retMsg')}")
            batch = result["result"]["list"]
            if not batch:
                break
            for r in batch:
                rows[int(r[0])] = [int(r[0]), *map(float, r[1:7])]
            next_cursor = min(int(r[0]) for r in batch) - 1
            if next_cursor >= cursor:
                raise ValueError("La pagination Bybit n'avance plus.")
            cursor = next_cursor
            if len(batch) < 1000:
                break
    else:
        cursor = start
        while cursor < end:
            q = urllib.parse.urlencode(dict(symbol=symbol + "USDT", interval="1h", limit=1000, startTime=cursor, endTime=end - 1))
            batch = get_json("https://api.binance.com/api/v3/klines?" + q)
            if not isinstance(batch, list):
                raise ValueError(f"Binance: {batch.get('msg')}")
            if not batch:
                break
            for r in batch:
                rows[int(r[0])] = [int(r[0]), *map(float, r[1:6]), float(r[7])]
            next_cursor = int(batch[-1][0]) + 3_600_000
            if next_cursor <= cursor:
                raise ValueError("La pagination Binance n'avance plus.")
            cursor = next_cursor
    df = pd.DataFrame([r for t, r in sorted(rows.items()) if start <= t and t + 3_600_000 <= end], columns=COLUMNS)
    df.timestamps = pd.to_datetime(df.timestamps, unit="ms", utc=True)
    validate_frame(df)
    return df


def prepare(start="2023-08-01", end="2026-10-21"):
    DATA.mkdir(exist_ok=True)
    start_ms, end_ms = (int(pd.Timestamp(x, tz="UTC").timestamp() * 1000) for x in (start, end))
    if end_ms > int(time.time() * 1000):
        raise ValueError("La date de fin doit être passée.")
    manifest = dict(start=start, end_exclusive=end, assets={})
    for symbol in SYMBOLS:
        df = download(symbol, start_ms, end_ms)
        grouped = df.set_index("timestamps").resample("4h", origin="epoch")
        four = grouped.agg(dict(open="first", high="max", low="min", close="last", volume="sum", amount="sum"))
        four = four[grouped.close.count() == 4].reset_index()
        for tf, frame in (("1h", df), ("4h", four)):
            validate_frame(frame)
            path = DATA / f"{symbol}_{tf}.csv"
            frame.to_csv(path, index=False)
            step = pd.Timedelta(hours=1 if tf == "1h" else 4)
            manifest["assets"][f"{symbol}_{tf}"] = dict(rows=len(frame), start=frame.timestamps.iloc[0].isoformat(),
                end=frame.timestamps.iloc[-1].isoformat(), gaps=int((frame.timestamps.diff().dropna() != step).sum()),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), source="Bybit spot" if symbol == "HYPE" else "Binance spot")
        print(symbol, len(df), "bougies 1h avec volumes", flush=True)
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2023-08-01")
    parser.add_argument("--end", default="2026-10-21")
    args = parser.parse_args()
    prepare(args.start, args.end)
