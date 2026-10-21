"""Checks the causal boundaries on which the experiment's conclusions depend."""
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kronos_experiment import anchors, baseline, normalize_window, sparse_starts, CONTEXT, HORIZON


class ExperimentTests(unittest.TestCase):
    def frame(self):
        n = 900
        close = 100 * np.exp(np.sin(np.arange(n) / 17) * .02 + np.arange(n) * .0001)
        return pd.DataFrame(dict(timestamps=pd.date_range('2025-10-01', periods=n, freq='h', tz='UTC'),
                                 open=close, high=close * 1.01, low=close * .99, close=close,
                                 volume=np.full(n, 20), amount=close * 20))

    def test_split_contains_all_targets_and_no_gaps(self):
        f = self.frame()
        lo, hi = f.timestamps.iloc[500], f.timestamps.iloc[700]
        indices = anchors(f, 3600000, lo, hi)
        self.assertGreater(len(indices), 0)
        self.assertTrue(all(f.timestamps.iloc[i+1] >= lo and f.timestamps.iloc[i+HORIZON] < hi for i in indices))
        f.loc[550, 'timestamps'] = f.timestamps.iloc[549]
        gapped = anchors(f, 3600000, lo, hi)
        self.assertTrue(all(not (i - CONTEXT + 1 <= 550 <= i + HORIZON) for i in gapped))

    def test_future_targets_cannot_change_context_normalization(self):
        rng = np.random.default_rng(1)
        window = rng.normal(size=(CONTEXT + HORIZON, 6)).astype(np.float32)
        first = normalize_window(window)
        window[CONTEXT:] *= 1000
        second = normalize_window(window)
        np.testing.assert_array_equal(first[:CONTEXT], second[:CONTEXT])

    def test_future_prices_cannot_change_simple_baseline(self):
        f = self.frame()
        before = baseline(f, 600)
        f.loc[601:, ['high','low','close']] *= 10
        self.assertEqual(before, baseline(f, 600))

    def test_diagnostic_outcomes_do_not_overlap(self):
        chosen = sparse_starts(np.arange(400, 900), 35)
        self.assertTrue(all(b-a >= HORIZON for a,b in zip(chosen, chosen[1:])))


if __name__ == '__main__':
    unittest.main()
