"""Concurrency, model identity and API regressions without loading model weights."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kronos_service import KronosService
import server
from kronos_runtime import gpu_slot


class ForecastTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        lock_path = patch("kronos_runtime.GPU_LOCK", Path(directory.name) / "gpu.lock")
        lock_path.start()
        self.addCleanup(lock_path.stop)
        self.rows = [(i * 3600000, 100, 102, 98, 101, 20, 2020) for i in range(400)]
        self.calls = []
        self.loads = []

        def load(model):
            self.loads.append(model)
            return model

        def infer(predictor, rows, times, model, seed):
            self.calls.append(model)
            time.sleep(.03)
            return [[101] * len(times)] * 50

        self.service = KronosService(load, infer, capacity=2)

    def forecast(self, model="original", symbol="ETH"):
        return self.service.forecast(symbol, "1h", "test", self.rows, 3600000, model)

    def test_concurrent_identical_requests_compute_once(self):
        barrier = threading.Barrier(4)
        def run(_):
            barrier.wait()
            return self.forecast()
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(run, range(4)))
        self.assertEqual(self.loads, ["original"])
        self.assertEqual(self.calls, ["original"])
        self.assertTrue(all(r is results[0] for r in results))
        self.assertEqual(len(results[0]["times"]), 12)
        self.assertEqual(results[0]["times"][0], 400 * 3600)

    @patch("kronos_service.available", return_value=True)
    def test_cache_separates_models_and_is_bounded(self, _):
        self.forecast()
        tuned = self.forecast("crypto-v1")
        self.assertEqual(tuned["model"], "crypto-v1")
        self.forecast(symbol="BTC")
        self.forecast()
        self.assertEqual(len(self.service.cache), 2)
        self.assertEqual(len(self.calls), 4)

    def test_changed_closed_candle_invalidates_cache(self):
        self.forecast()
        self.rows[-1] = (*self.rows[-1][:4], 100.5, 20, 2010)
        self.forecast()
        self.assertEqual(len(self.calls), 2)

    def test_gap_is_rejected_before_loading_model(self):
        self.rows[250] = (self.rows[249][0], *self.rows[250][1:])
        with self.assertRaisesRegex(ValueError, "manquantes"):
            self.forecast()
        self.assertFalse(self.loads)

    def test_invalid_api_parameters_return_json(self):
        with server.app.test_client() as client:
            for query in ("sym=ETH&tf=wrong", "sym=%3Cscript%3E", "sym=ETH&src=wrong", ""):
                response = client.get("/api/kronos?" + query)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json)

    def test_empty_watchlist_is_valid(self):
        response = server.app.test_client().get("/api/watch?syms=")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, [])

    def test_busy_training_lock_prevents_loading_or_inference(self):
        with gpu_slot():
            with self.assertRaises(BlockingIOError):
                self.forecast()
        self.assertFalse(self.loads)
        self.assertFalse(self.calls)

    def test_api_excludes_forming_candle_and_echoes_source(self):
        now = int(time.time() * 1000)
        step = 3600000
        last = now // step * step
        rows = [(last - (400 - i) * step, 100, 102, 98, 101, 20, 2020) for i in range(401)]
        with patch.object(server, "candles", return_value=dict(rows=rows, src="test")), patch.object(server, "kronos", self.service):
            response = server.app.test_client().get("/api/kronos?sym=ETH&tf=1h&src=hl_spot")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["start"]["time"], (last - step) // 1000)
        self.assertEqual(response.json["times"][0], last // 1000)
        self.assertEqual(response.json["source"], "hl_spot")


if __name__ == "__main__":
    unittest.main()
