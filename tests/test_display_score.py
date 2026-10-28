"""Display-score stretch (fides_scoring.display_score) checks (stdlib unittest)."""
from __future__ import annotations

import unittest

from fides_config import VerdictThresholds
from fides_scoring import DISPLAY_ANCHORS, display_score


class DisplayScoreTest(unittest.TestCase):
    def test_hits_every_anchor(self):
        for raw, shown in DISPLAY_ANCHORS:
            self.assertAlmostEqual(display_score(raw), shown)

    def test_verdict_thresholds_land_on_round_numbers(self):
        t = VerdictThresholds()
        self.assertAlmostEqual(display_score(t.suspected), 20.0)
        self.assertAlmostEqual(display_score(t.normal), 40.0)
        self.assertAlmostEqual(display_score(t.credible), 95.0)

    def test_monotonic_and_bounded(self):
        values = [display_score(x / 10) for x in range(-50, 1100)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(min(values), 0.0)
        self.assertEqual(max(values), 100.0)

    def test_midpoint_is_linear(self):
        # 45 → 55, 52 → 70 사이 가운데는 62.5
        self.assertAlmostEqual(display_score(48.5), 62.5)


if __name__ == "__main__":
    unittest.main()
