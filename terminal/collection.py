"""Durable public spot candles and forecasts recorded before their target closes.

No historical predictions are backfilled. SQLite is local, and importing this module
does not create a database, start a thread, access the network or load a model.
"""
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from pathlib import Path
import sqlite3
import statistics
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kronos_runtime import CONTEXT, HORIZON

SYMBOLS = ("BTC", "ETH", "HYPE", "ZEC")
STEPS = {"1h": 3_600_000, "4h": 14_400_000}
MODELS = ("original", "crypto-v2")
DB_PATH = Path(__file__).resolve().parent / "data" / "hyperliquid.sqlite3"
LOG = logging.getLogger(__name__)


class Archive:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS streams (
                    sym TEXT, tf TEXT, coin TEXT, market TEXT, checked_ms INTEGER,
                    error TEXT, forecast_error TEXT, PRIMARY KEY(sym,tf));
                CREATE TABLE IF NOT EXISTS candles (
                    coin TEXT, tf TEXT, t INTEGER, o REAL, h REAL, l REAL, c REAL,
                    v REAL, amount_estimate REAL, raw TEXT,
                    first_seen_ms INTEGER, last_seen_ms INTEGER,
                    PRIMARY KEY(coin,tf,t));
                CREATE TABLE IF NOT EXISTS forecasts (
                    id INTEGER PRIMARY KEY, sym TEXT, coin TEXT, tf TEXT,
                    anchor_ms INTEGER, recorded_ms INTEGER, first_close_ms INTEGER,
                    end_ms INTEGER, context TEXT, predictions TEXT,
                    evaluated_ms INTEGER, evaluation TEXT,
                    UNIQUE(coin,tf,anchor_ms));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def stream(self, sym, tf):
        with self.connect() as db:
            row = db.execute("SELECT * FROM streams WHERE sym=? AND tf=?", (sym, tf)).fetchone()
            return dict(row) if row else None

    def error(self, sym, tf, message, forecast=False):
        column = "forecast_error" if forecast else "error"
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO streams(sym,tf) VALUES (?,?)", (sym, tf))
            db.execute(f"UPDATE streams SET {column}=? WHERE sym=? AND tf=?", (message, sym, tf))

    def ingest(self, sym, tf, coin, market, raw, now):
        step = STEPS[tf]
        rows = {}
        for item in raw:
            t = int(item["t"])
            if t + step > now - 5000:  # allow the exchange five seconds to finish the candle
                continue
            values = [float(item[k]) for k in ("o", "h", "l", "c", "v")]
            o, h, l, c, v = values
            if (item["s"] != coin or item["i"] != tf or t % step or
                    not all(math.isfinite(x) for x in values) or min(o, h, l, c) <= 0 or
                    v < 0 or l > min(o, c) or h < max(o, c)):
                raise ValueError("Bougie invalide ou marché différent : lot refusé.")
            rows[t] = (coin, tf, t, *values, v * (o + h + l + c) / 4,
                       json.dumps(item, sort_keys=True), now, now)
        if not rows:
            raise ValueError("Aucune bougie clôturée reçue.")
        with self.connect() as db:
            db.executemany("""INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(coin,tf,t) DO UPDATE SET
                o=excluded.o,h=excluded.h,l=excluded.l,c=excluded.c,v=excluded.v,
                amount_estimate=excluded.amount_estimate,raw=excluded.raw,last_seen_ms=excluded.last_seen_ms
                """, rows.values())
            db.execute("""INSERT INTO streams(sym,tf,coin,market,checked_ms,error) VALUES (?,?,?,?,?,NULL)
                ON CONFLICT(sym,tf) DO UPDATE SET coin=excluded.coin,market=excluded.market,
                checked_ms=excluded.checked_ms,error=NULL""", (sym, tf, coin, market, now))

    def history(self, coin, tf, n=CONTEXT):
        with self.connect() as db:
            rows = db.execute("""SELECT t,o,h,l,c,v,amount_estimate FROM candles
                WHERE coin=? AND tf=? ORDER BY t DESC LIMIT ?""", (coin, tf, n)).fetchall()
            return [tuple(r) for r in reversed(rows)]

    def due(self, coin, tf, anchor):
        with self.connect() as db:
            end = db.execute("SELECT MAX(end_ms) FROM forecasts WHERE coin=? AND tf=?", (coin, tf)).fetchone()[0]
            # No overlapping targets within one market/timeframe, including after restart.
            return end is None or anchor + STEPS[tf] >= end

    def record(self, sym, coin, tf, rows, predictions, now):
        step, anchor = STEPS[tf], rows[-1][0]
        first_close, end = anchor + 2 * step, anchor + (HORIZON + 1) * step
        expected = [(anchor + i * step) // 1000 for i in range(1, HORIZON + 1)]
        if len(rows) != CONTEXT or any(b[0] - a[0] != step for a, b in zip(rows, rows[1:])):
            raise ValueError("Contexte incomplet.")
        if not anchor + step <= now < first_close or set(predictions) != set(MODELS):
            raise ValueError("Prévision trop tardive ou comparaison incomplète.")
        stream = self.stream(sym, tf)
        for model, p in predictions.items():
            if (p["sym"] != sym or p["tf"] != tf or p["model"] != model or
                    not stream or stream["coin"] != coin or p["src"] != f"Hyperliquid spot {stream['market']}" or
                    p["start"] != dict(time=anchor // 1000, value=rows[-1][4]) or p["times"] != expected or
                    not anchor + step <= p["generated_at"] * 1000 <= now or
                    len(p["paths"]) != 50 or any(len(path) != HORIZON or
                    any(not math.isfinite(x) or x <= 0 for x in path) for path in p["paths"])):
                raise ValueError("Prévision incohérente avec le contexte archivé.")
        with self.connect() as db:
            latest = db.execute("SELECT anchor_ms,end_ms FROM forecasts WHERE coin=? AND tf=? ORDER BY anchor_ms DESC LIMIT 1",
                                (coin, tf)).fetchone()
            if latest and anchor != latest["anchor_ms"] and anchor + step < latest["end_ms"]:
                raise ValueError("Les cibles de cette prévision chevauchent une comparaison enregistrée.")
            db.execute("""INSERT OR IGNORE INTO forecasts
                (sym,coin,tf,anchor_ms,recorded_ms,first_close_ms,end_ms,context,predictions)
                VALUES (?,?,?,?,?,?,?,?,?)""", (sym, coin, tf, anchor, now, first_close, end,
                json.dumps(rows), json.dumps(predictions)))

    def evaluate(self, now):
        with self.connect() as db:
            pending = db.execute("SELECT * FROM forecasts WHERE evaluation IS NULL AND end_ms<=?", (now,)).fetchall()
            for f in pending:
                step = STEPS[f["tf"]]
                actual = db.execute("""SELECT t,c FROM candles WHERE coin=? AND tf=?
                    AND t>? AND t<? ORDER BY t""", (f["coin"], f["tf"], f["anchor_ms"], f["end_ms"])).fetchall()
                if [r["t"] for r in actual] != [f["anchor_ms"] + step * i for i in range(1, HORIZON + 1)]:
                    continue  # missing observations never count as a successful prediction
                anchor = json.loads(f["context"])[-1][4]
                observed = actual[-1]["c"]
                predictions = json.loads(f["predictions"])
                scores = {}
                for model, p in predictions.items():
                    predicted = statistics.mean(path[-1] for path in p["paths"])
                    sign = lambda x: (x > 0) - (x < 0)
                    scores[model] = dict(error_bps=abs(predicted - observed) / anchor * 10000,
                                         direction=sign(predicted - anchor) == sign(observed - anchor))
                evaluation = dict(actual=[list(r) for r in actual], scores=scores,
                                  unchanged_bps=abs(anchor - observed) / anchor * 10000)
                db.execute("UPDATE forecasts SET evaluated_ms=?,evaluation=? WHERE id=? AND evaluation IS NULL",
                           (now, json.dumps(evaluation), f["id"]))

    def status(self, now):
        with self.connect() as db:
            streams = []
            for sym in SYMBOLS:
                for tf, step in STEPS.items():
                    row = db.execute("SELECT * FROM streams WHERE sym=? AND tf=?", (sym, tf)).fetchone()
                    s = dict(row) if row else dict(sym=sym, tf=tf, error=None, forecast_error=None)
                    count, first, last = db.execute("SELECT COUNT(*),MIN(t),MAX(t) FROM candles WHERE coin=? AND tf=?",
                                                    (s.get("coin"), tf)).fetchone()
                    s.update(count=count, first_ms=first, last_ms=last,
                             missing=(last - first) // step + 1 - count if count else 0,
                             fresh=last is not None and last >= (now - 5000) // step * step - step)
                    streams.append(s)
            counts = dict(db.execute("""SELECT COUNT(*) AS recorded, COUNT(evaluation) AS evaluated,
                MIN(CASE WHEN evaluation IS NULL THEN end_ms END) AS next_end_ms FROM forecasts""").fetchone())
            counts["pending"] = counts["recorded"] - counts["evaluated"]
            counts["overdue"] = db.execute("SELECT COUNT(*) FROM forecasts WHERE evaluation IS NULL AND end_ms<=?", (now,)).fetchone()[0]
            groups = {}
            for row in db.execute("SELECT tf,predictions,evaluation FROM forecasts WHERE evaluation IS NOT NULL"):
                evaluation, predictions = json.loads(row["evaluation"]), json.loads(row["predictions"])
                for model, score in evaluation["scores"].items():
                    revision = predictions[model]["checkpoint_sha256"]
                    group = groups.setdefault((row["tf"], model, revision), [])
                    group.append((score["error_bps"], evaluation["unchanged_bps"], score["direction"]))
            scores = [dict(tf=tf, model=model, revision=rev, n=len(items),
                           error_bps=statistics.mean(x[0] for x in items),
                           unchanged_bps=statistics.mean(x[1] for x in items),
                           direction=statistics.mean(x[2] for x in items))
                      for (tf, model, rev), items in groups.items()]
            return dict(streams=streams, candles=sum(s["count"] for s in streams), forecasts=counts, scores=scores)

    def export(self, directory):
        """A consistent OHLCVA snapshot for later experiments, never an automatic training input."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        manifest = dict(created_at=datetime.now(timezone.utc).isoformat(), source="Hyperliquid spot",
                        amount="estimate: volume * mean(open,high,low,close)", assets={})
        with self.connect() as db:
            db.execute("BEGIN")  # one read snapshot even if the collector writes meanwhile
            streams = db.execute("SELECT * FROM streams WHERE coin IS NOT NULL ORDER BY sym,tf").fetchall()
            for s in streams:
                rows = db.execute("""SELECT t,o,h,l,c,v,amount_estimate FROM candles
                    WHERE coin=? AND tf=? ORDER BY t""", (s["coin"], s["tf"])).fetchall()
                if not rows:
                    continue
                name = f"{s['sym']}_{s['tf']}"
                path = directory / f"{name}.csv"
                with path.open("w", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["timestamps", "open", "high", "low", "close", "volume", "amount"])
                    writer.writerows([datetime.fromtimestamp(r[0] / 1000, timezone.utc).isoformat(), *r[1:]] for r in rows)
                manifest["assets"][name] = dict(coin=s["coin"], market=s["market"], rows=len(rows),
                    first_ms=rows[0][0], last_ms=rows[-1][0],
                    missing=(rows[-1][0] - rows[0][0]) // STEPS[s["tf"]] + 1 - len(rows),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest


class Collector:
    def __init__(self, get, resolve, service, path=DB_PATH, clock=time.time):
        self.archive = Archive(path)
        self.get, self.resolve, self.service, self.clock = get, resolve, service, clock
        self.stop_event = threading.Event()
        self.thread = None
        self.checkpoints = {}
        self.last_cycle_ms = None
        self.phase = "Initialisation"

    def checkpoint(self, model):
        from kronos_service import MODELS as registry
        path = Path(registry[model]["path"]) / "model.safetensors"
        if not path.is_file():
            from huggingface_hub import try_to_load_from_cache
            cached = try_to_load_from_cache(registry[model]["path"], "model.safetensors")
            if not isinstance(cached, str):
                raise LookupError("Poids non retrouvés pour identifier la prévision.")
            path = Path(cached)
        key = (str(path), path.stat().st_mtime_ns)
        if key not in self.checkpoints:
            with path.open("rb") as handle:
                self.checkpoints[key] = hashlib.file_digest(handle, "sha256").hexdigest()
        return self.checkpoints[key]

    def collect(self, sym, tf):
        now, step = int(self.clock() * 1000), STEPS[tf]
        market = self.resolve(sym)
        if not market:
            raise LookupError("Spot USDC introuvable ; aucun remplacement par un perp.")
        coin, label = market
        previous = self.archive.history(coin, tf, 1)
        start = max(0, now - 5000 * step) if not previous else max(0, previous[-1][0] - 2 * step)
        raw = self.get("https://api.hyperliquid.xyz/info", dict(type="candleSnapshot", req=dict(
            coin=coin, interval=tf, startTime=start, endTime=now)))
        self.archive.ingest(sym, tf, coin, label, raw, now)

    def predict(self, sym, tf):
        from kronos_service import available
        s = self.archive.stream(sym, tf)
        if not s or s["error"] or not s["coin"]:
            return
        rows = self.archive.history(s["coin"], tf)
        if not rows:
            return
        now, step, anchor = int(self.clock() * 1000), STEPS[tf], rows[-1][0]
        if not self.archive.due(s["coin"], tf, anchor):
            self.archive.error(sym, tf, None, forecast=True)
            return
        if anchor != now // step * step - step:
            raise ValueError("Dernière bougie encore indisponible ; prévision reportée.")
        if not all(available(m) for m in MODELS):
            raise LookupError("Original et V2 sont nécessaires à la comparaison.")
        predictions = {}
        for model in MODELS:
            self.phase = f"Prévision {sym} {tf} · {model}"
            p = self.service.forecast(sym, tf, f"Hyperliquid spot {s['market']}", rows, step, model)
            predictions[model] = dict(p, checkpoint_sha256=self.checkpoint(model),
                                     sampling=dict(paths=50, temperature=1.0, top_p=0.9))
        self.archive.record(sym, s["coin"], tf, rows, predictions, int(self.clock() * 1000))
        self.archive.error(sym, tf, None, forecast=True)

    def cycle(self):
        # Finish all data requests before using the GPU; a failed market cannot stop the others.
        for sym in SYMBOLS:
            for tf in STEPS:
                if self.stop_event.is_set():
                    return
                self.phase = f"Collecte {sym} {tf}"
                try:
                    self.collect(sym, tf)
                except Exception as exc:
                    self.archive.error(sym, tf, str(exc))
                    LOG.warning("Collection %s %s: %s", sym, tf, exc)
        self.archive.evaluate(int(self.clock() * 1000))
        for sym in SYMBOLS:
            for tf in STEPS:
                if self.stop_event.is_set():
                    return
                try:
                    self.predict(sym, tf)
                except Exception as exc:
                    self.archive.error(sym, tf, str(exc), forecast=True)
                    LOG.warning("Forecast archive %s %s: %s", sym, tf, exc)
        self.last_cycle_ms = int(self.clock() * 1000)
        self.phase = "En veille · prochaine collecte dans une minute"

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.cycle()
            except Exception:
                self.phase = "Erreur de collecte · nouvel essai dans une minute"
                LOG.exception("Collector cycle failed")
            self.stop_event.wait(60)

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, name="hyperliquid-collector", daemon=True)
            self.thread.start()

    def status(self):
        return dict(self.archive.status(int(self.clock() * 1000)),
                    running=self.thread is not None and self.thread.is_alive(),
                    phase=self.phase, last_cycle_ms=self.last_cycle_ms)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Exporter les bougies spot archivées, sans relancer une collecte.")
    parser.add_argument("--export", type=Path, required=True, help="Nouveau dossier de destination (ne doit pas exister).")
    args = parser.parse_args()
    result = Archive().export(args.export)
    print(json.dumps(result, indent=2))
