"""Focused checks for surrogate scoring and temporal isolation."""

import tempfile
import unittest
from pathlib import Path

from scripts.backtest_t4 import common_task, save_case, validate_and_score


class BacktestChecks(unittest.TestCase):
    def test_future_auction_row_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = common_task("auction_demand", "regression", "bid_to_cover_ratio",
                               "2024-09-30", "2024-10-25", [{"entity_id": "A"}], "Forecast")
            doc = {"doc_id": "HISTORY", "doc_date": "2024-09-25",
                   "text": "2024-10-25 | 2-Year | new | 1 | 2.5 | 4 | 60"}
            with self.assertRaisesRegex(ValueError, "Future auction date leaked"):
                save_case(root, "auction", "bt-auction-2024-10", task, [doc],
                          {"A": {"value": 2.5, "date": "2024-10-25"}}, [])
            self.assertFalse((root / "auction" / "bt-auction-2024-10").exists())

    def test_quality_and_coverage_match_published_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = common_task("auction_demand", "regression", "bid_to_cover_ratio",
                               "2024-09-30", "2024-10-25",
                               [{"entity_id": "A"}, {"entity_id": "B"}], "Forecast")
            doc = {"doc_id": "HISTORY", "doc_date": "2024-09-25", "text": "known history"}
            save_case(root, "auction", "example", task, [doc],
                      {"A": {"value": 1.0}, "B": {"value": 3.0}}, [])
            answer = {"task_id": "example", "target_type": "regression",
                      "entity_predictions": [
                          {"entity_id": eid, "point_forecast": point,
                           "interval": {"level": 0.9, "lo": point - 0.1, "hi": point + 0.1},
                           "claims": [{"doc_id": "HISTORY", "span_start": 0, "span_end": 5}]}
                          for eid, point in (("A", 1.0), ("B", 3.0))]}
            metrics = validate_and_score(root / "auction" / "example", answer)
            self.assertEqual(metrics["quality"], 1.0)
            self.assertEqual(metrics["coverage"], 1.0)
            self.assertAlmostEqual(metrics["score_without_nli"], 0.67)


if __name__ == "__main__":
    unittest.main()
