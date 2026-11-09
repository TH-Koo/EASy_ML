import unittest

from server import build_claims


def cap(cap_id, positive, sources=(), ratio=0.0):
    return {
        "capability_id": cap_id,
        "capability_name_ko": cap_id,
        "positive_claim": positive,
        "supporting_sources": list(sources),
        "required_fulfillment_ratio": ratio,
        "matched_strong_patterns": [],
        "missing_required_components": [],
    }


class BuildClaimsTest(unittest.TestCase):
    def test_drops_capabilities_the_ad_never_claimed(self):
        claims = build_claims([
            cap("CAP_DISPLAY_OPTIMIZATION", True, ["kipris"], 0.5),
            cap("CAP_DRY_COURSE", False, ["kipris"], 0.5),
            cap("CAP_COOKING_MODE", False),
        ])
        self.assertEqual([c["id"] for c in claims], ["CAP_DISPLAY_OPTIMIZATION"])
        self.assertEqual(claims[0]["status"], "partial")

    def test_keeps_old_records_without_flag(self):
        row = cap("CAP_RECOMMENDATION", True)
        del row["positive_claim"]
        self.assertEqual(len(build_claims([row])), 1)


if __name__ == "__main__":
    unittest.main()
