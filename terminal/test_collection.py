"""Archive invariants: closed data, fixed prospective forecasts, and fair outcomes."""
from copy import deepcopy
import csv
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collection import Archive, Collector, STEPS, MODELS

STEP = STEPS["1h"]


def candle(i, close=100, coin="@151"):
    return dict(t=i * STEP, T=(i + 1) * STEP - 1, s=coin, i="1h", o="100",
                h=str(max(101, close)), l="99", c=str(close), v="20", n=7)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "archive.sqlite3"
        self.archive = Archive(self.path)
        self.now = 400 * STEP + 60000
        self.raw = [candle(i) for i in range(401)]
        self.archive.ingest("BTC", "1h", "@151", "UBTC/USDC", self.raw, self.now)
        self.rows = self.archive.history("@151", "1h")
        self.predictions = {model: dict(sym="BTC", tf="1h", model=model,
            src="Hyperliquid spot UBTC/USDC", start=dict(time=399 * 3600, value=100),
            generated_at=self.now // 1000, times=[i * 3600 for i in range(400, 412)],
            checkpoint_sha256=model, paths=[[110] * 12 for _ in range(50)]) for model in MODELS}

    def record(self, predictions=None, now=None):
        self.archive.record("BTC", "@151", "1h", self.rows,
                            predictions or self.predictions, self.now if now is None else now)

    def test_closed_only_upsert_and_raw_provenance(self):
        self.assertEqual(len(self.rows), 400)
        self.assertEqual(self.rows[-1][0], 399 * STEP)
        revised = candle(399, 101)
        self.archive.ingest("BTC", "1h", "@151", "UBTC/USDC", [revised], self.now + 10000)
        with self.archive.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 400)
            r = db.execute("SELECT * FROM candles WHERE t=?", (399 * STEP,)).fetchone()
            self.assertEqual(r["c"], 101)
            self.assertEqual(r["first_seen_ms"], self.now)
            self.assertEqual(r["last_seen_ms"], self.now + 10000)
            self.assertIn('"n": 7', r["raw"])

    def test_invalid_batch_and_wrong_market_are_rejected_atomically(self):
        for bad in (candle(398, float("nan")), candle(398, coin="BTC")):
            with self.assertRaises(ValueError):
                self.archive.ingest("BTC", "1h", "@151", "UBTC/USDC", [candle(399, 110), bad], self.now)
        self.assertEqual(self.archive.history("@151", "1h")[-1][4], 100)

    def test_duplicates_and_restarts_preserve_predictions_and_context(self):
        self.record()
        changed = deepcopy(self.predictions)
        changed["original"]["paths"][0][-1] = 999
        self.record(changed)
        restarted = Archive(self.path)
        with restarted.connect() as db:
            saved = db.execute("SELECT * FROM forecasts").fetchall()
        self.assertEqual(len(saved), 1)
        self.assertNotIn("999", saved[0]["predictions"])
        self.assertFalse(restarted.due("@151", "1h", 410 * STEP))
        self.assertTrue(restarted.due("@151", "1h", 411 * STEP))

    def test_late_forecasts_wrong_source_and_incomplete_pairs_are_rejected(self):
        with self.assertRaises(ValueError):
            self.record(now=401 * STEP)
        for modify in (lambda p: p.pop("crypto-v2"),
                       lambda p: p["original"].update(src="Hyperliquid perp"),
                       lambda p: p["original"].update(times=[0] * 12)):
            predictions = deepcopy(self.predictions)
            modify(predictions)
            with self.assertRaises(ValueError):
                self.record(predictions)

    def test_no_score_until_all_targets_close_and_arrive(self):
        self.record()
        end = 412 * STEP
        self.archive.ingest("BTC", "1h", "@151", "UBTC/USDC",
                            [candle(i, 105) for i in range(400, 411)], end + 6000)
        self.archive.evaluate(end + 6000)
        state = self.archive.status(end + 6000)
        self.assertEqual(state["forecasts"]["evaluated"], 0)
        self.assertEqual(state["forecasts"]["overdue"], 1)
        self.archive.ingest("BTC", "1h", "@151", "UBTC/USDC", [candle(411, 108)], end + 6000)
        self.archive.evaluate(end - 1)
        self.assertEqual(self.archive.status(end)["forecasts"]["evaluated"], 0)
        self.archive.evaluate(end + 6000)
        state = self.archive.status(end + 6000)
        self.assertEqual(state["forecasts"]["evaluated"], 1)
        for score in state["scores"]:
            self.assertEqual(score["error_bps"], 200)
            self.assertEqual(score["unchanged_bps"], 800)
            self.assertEqual(score["direction"], 1)
        # Late provider corrections cannot rewrite an already evaluated result.
        self.archive.ingest("BTC", "1h", "@151", "UBTC/USDC", [candle(411, 200)], end + 7000)
        self.archive.evaluate(end + 7000)
        self.assertEqual(self.archive.status(end + 7000)["scores"], state["scores"])

    def test_gaps_staleness_and_errors_remain_visible(self):
        with self.archive.connect() as db:
            db.execute("DELETE FROM candles WHERE t=?", (200 * STEP,))
        self.archive.error("BTC", "1h", "Network failure")
        state = self.archive.status(self.now + STEP)
        btc = next(s for s in state["streams"] if s["sym"] == "BTC" and s["tf"] == "1h")
        self.assertEqual(btc["count"], 399)
        self.assertEqual(btc["missing"], 1)
        self.assertFalse(btc["fresh"])
        self.assertEqual(btc["error"], "Network failure")

    def test_collector_does_not_substitute_perp_and_catches_up(self):
        get, resolve = Mock(return_value=[candle(399), candle(400)]), Mock(return_value=None)
        collector = Collector(get, resolve, Mock(), self.path, clock=lambda: self.now / 1000)
        with self.assertRaisesRegex(LookupError, "Spot"):
            collector.collect("BTC", "1h")
        get.assert_not_called()
        resolve.return_value = ("@151", "UBTC/USDC")
        collector.collect("BTC", "1h")
        request = get.call_args.args[1]["req"]
        self.assertEqual(request["coin"], "@151")
        self.assertEqual(request["startTime"], 397 * STEP)

    def test_export_matches_snapshot_and_refuses_overwrite(self):
        destination = self.path.parent / "export"
        manifest = self.archive.export(destination)
        path = destination / "BTC_1h.csv"
        with path.open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 400)
        self.assertEqual(float(rows[-1]["close"]), 100)
        self.assertEqual(float(rows[-1]["amount"]), 2000)
        self.assertEqual(manifest["assets"]["BTC_1h"]["coin"], "@151")
        self.assertEqual(manifest["assets"]["BTC_1h"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(FileExistsError):
            self.archive.export(destination)

    def test_local_api_reports_archive_counts_and_pending_outcomes(self):
        import server
        self.record()
        collector = Collector(Mock(), Mock(), Mock(), self.path, clock=lambda: self.now / 1000)
        with patch.object(server, "collector", collector):
            response = server.app.test_client().get("/api/collection")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["candles"], 400)
        self.assertEqual(response.json["forecasts"]["pending"], 1)
        self.assertEqual(response.json["scores"], [])
        self.assertFalse(response.json["running"])

    @patch("kronos_service.available", return_value=True)
    def test_busy_model_does_not_archive_half_pair_and_retries(self, _):
        service = Mock()
        service.forecast.side_effect = BlockingIOError("GPU occupé")
        collector = Collector(Mock(), Mock(), service, self.path, clock=lambda: self.now / 1000)
        with self.assertRaises(BlockingIOError):
            collector.predict("BTC", "1h")
        self.assertEqual(self.archive.status(self.now)["forecasts"]["recorded"], 0)
        service.forecast.side_effect = lambda sym, tf, src, rows, step, model: self.predictions[model]
        with patch.object(collector, "checkpoint", return_value="test-checkpoint"):
            collector.predict("BTC", "1h")
        self.assertEqual(self.archive.status(self.now)["forecasts"]["recorded"], 1)
        calls = service.forecast.call_count
        collector.predict("BTC", "1h")
        self.assertEqual(service.forecast.call_count, calls)


if __name__ == "__main__":
    unittest.main()
