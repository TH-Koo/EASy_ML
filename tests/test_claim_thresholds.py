import unittest

from fides_config import DEFAULT_CLAIM_THRESHOLDS


class ClaimThresholdsTest(unittest.TestCase):
    def test_bands_and_boundaries(self):
        cases = [
            (0.0, "unsupported"),
            (0.3499, "unsupported"),
            (0.35, "partial"),
            (0.38, "partial"),
            (0.5999, "partial"),
            (0.60, "verified"),
            (0.6429, "verified"),
            (0.8192, "verified"),
            (1.0, "verified"),
        ]
        for support, expected in cases:
            with self.subTest(support=support):
                self.assertEqual(DEFAULT_CLAIM_THRESHOLDS.classify(support, True), expected)

    def test_sources_are_required_even_for_high_support(self):
        self.assertEqual(DEFAULT_CLAIM_THRESHOLDS.classify(1.0, False), "unsupported")


if __name__ == "__main__":
    unittest.main()
