"""Focused regression checks for portable Suspicious-only corrections."""
from __future__ import annotations

import copy
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from fides_ml.s_only import (
    FEATURE_COLUMNS, PortableSOnlyModel, apply_s_only, load_s_only_predictor, verdict_label,
)


VERDICTS = {
    "washing": "AI 워싱 상품 / Washing",
    "genuine": "신뢰 상품 / Normal",
    "suspicious": "워싱 의심 상품 / Suspected",
    "not_evaluated": "AI 기능 주장 미확인 / Not Evaluated",
}


def constant_tree(probabilities):
    return {
        "children_left": [-1], "children_right": [-1], "feature": [-2],
        "threshold": [-2.0], "value": [list(probabilities)],
    }


def artifact(probabilities=(0.1, 0.8, 0.1), categories=("known",)):
    return {
        "format_version": 1, "policy": "suspicious_only",
        "labels": ["washing", "suspicious", "genuine"], "threshold": 0.55,
        "feature_columns": list(FEATURE_COLUMNS), "category_vocabulary": list(categories),
        "feature_medians": [0.5] * len(FEATURE_COLUMNS),
        "trees": [constant_tree(probabilities)], "metadata": {},
    }


def feature_row():
    row = {key: 0.5 for key in FEATURE_COLUMNS}
    for channel in ("hes", "tes", "ces"):
        row[channel] = 40.0
        row[f"mask_{channel}"] = 1.0
    row["ecs"] = 20.0
    return row


def analysis_result(label="washing"):
    with redirect_stdout(io.StringIO()):
        from analysis_engine import AnalysisResult
    channels = {}
    for channel in ("hes", "tes", "ces"):
        channels[channel] = {
            "score": 40.0, "evidence_count": 2, "source_types": ["seller_page"],
            "avg_directness": 0.5, "avg_recency": 0.5, "max_source_share": 1.0,
            "active": True,
        }
    return AnalysisResult(
        accs=37.0, raw_accs=40.0, hes=40.0, tes=40.0, ces=40.0, ecs=20.0,
        conf=20.0, verdict=VERDICTS[label], risk_level="높음" if label == "washing" else "낮음",
        top_capabilities=[], reasons=["Original engine reason"], capability_scores=[],
        details={
            "channel_details": channels,
            "dynamic_weighting": {
                "active_channels": ["hes", "tes", "ces"],
                "weights": {"hes": 0.35, "tes": 0.4, "ces": 0.25},
                "dynamic_accs": 37.0,
            },
            "dynamic_weight_log": {
                "verdict": VERDICTS[label], "risk_level": "높음" if label == "washing" else "낮음",
                "dynamic_accs": 37.0,
            },
            "claim_detection": {"detected": True},
        },
    )


class PortableSOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.json"

    def model(self, probabilities=(0.1, 0.8, 0.1), payload=None):
        self.path.write_text(json.dumps(payload or artifact(probabilities)), encoding="utf-8")
        return PortableSOnlyModel(self.path)

    def test_known_and_unknown_category_use_onehot_and_zero_vector(self):
        payload = artifact()
        payload["trees"] = [{
            "children_left": [1, -1, -1], "children_right": [2, -1, -1],
            "feature": [len(FEATURE_COLUMNS), -2, -2], "threshold": [0.5, -2.0, -2.0],
            "value": [[0.4, 0.4, 0.2], [0.8, 0.1, 0.1], [0.1, 0.8, 0.1]],
        }]
        model = self.model(payload=payload)
        probabilities = model.predict_rows([feature_row(), feature_row()], ["known", "new-category"])
        np.testing.assert_allclose(probabilities, [[0.1, 0.8, 0.1], [0.8, 0.1, 0.1]])
        self.assertTrue(model.predict_result(analysis_result(), "known")["category_known"])
        self.assertFalse(model.predict_result(analysis_result(), "new-category")["category_known"])

    def test_none_and_nan_follow_saved_medians_but_missing_keys_and_infinity_reject(self):
        payload = artifact()
        payload["trees"] = [{
            "children_left": [1, -1, -1], "children_right": [2, -1, -1],
            "feature": [list(FEATURE_COLUMNS).index("hes"), -2, -2],
            "threshold": [0.25, -2.0, -2.0],
            "value": [[0.4, 0.4, 0.2], [0.8, 0.1, 0.1], [0.1, 0.8, 0.1]],
        }]
        model = self.model(payload=payload)
        for value in (None, float("nan")):
            row = feature_row()
            row["hes"] = value
            np.testing.assert_allclose(model.predict_rows([row], ["known"]), [[0.1, 0.8, 0.1]])
        missing = feature_row()
        del missing["hes"]
        with self.assertRaises((ValueError, KeyError)):
            model.predict_rows([missing], ["known"])
        infinite = feature_row()
        infinite["hes"] = float("inf")
        with self.assertRaises(ValueError):
            model.predict_rows([infinite], ["known"])

    def test_result_features_use_scoring_mask_instead_of_channel_active_flag(self):
        payload = artifact()
        payload["trees"] = [{
            "children_left": [1, -1, -1], "children_right": [2, -1, -1],
            "feature": [list(FEATURE_COLUMNS).index("mask_ces"), -2, -2],
            "threshold": [0.5, -2.0, -2.0],
            "value": [[0.4, 0.4, 0.2], [0.8, 0.1, 0.1], [0.1, 0.8, 0.1]],
        }]
        result = analysis_result()
        result.details["dynamic_weighting"]["active_channels"] = ["hes", "tes"]
        result.details["channel_details"]["ces"]["active"] = True
        probabilities = self.model(payload=payload).predict_result(result, "known")["probabilities"]
        np.testing.assert_allclose(probabilities, [0.8, 0.1, 0.1])

    def test_threshold_inclusive_and_original_wg_only_become_s(self):
        for original in ("washing", "genuine"):
            for probabilities, corrected in [((0.3, 0.55, 0.15), True), ((0.3, 0.549, 0.151), False),
                                             ((0.8, 0.1, 0.1), False), ((0.1, 0.1, 0.8), False)]:
                with self.subTest(original=original, probabilities=probabilities):
                    result = analysis_result(original)
                    before = copy.deepcopy(result)
                    apply_s_only(result, self.model(probabilities), "known")
                    self.assertEqual(verdict_label(result.verdict), "suspicious" if corrected else original)
                    if corrected:
                        self.assertEqual(result.details["s_only_correction"]["reason_code"], "corrected_to_s")
                    else:
                        self.assertEqual(result.details["s_only_correction"]["status"], "unchanged")
                    for key in ("accs", "raw_accs", "hes", "tes", "ces", "ecs", "conf"):
                        self.assertEqual(getattr(result, key), getattr(before, key))
                    self.assertEqual(result.details["dynamic_weighting"], before.details["dynamic_weighting"])

    def test_s_and_not_evaluated_are_preserved(self):
        for label in ("suspicious", "not_evaluated"):
            with self.subTest(label=label):
                result = analysis_result(label)
                original = (result.verdict, result.risk_level)
                apply_s_only(result, self.model(), "known")
                self.assertEqual((result.verdict, result.risk_level), original)
                self.assertEqual(result.details["s_only_correction"]["reason_code"], "baseline_not_eligible")

    def test_input_errors_preserve_original_and_record_failure(self):
        result = analysis_result("genuine")
        result.ecs = float("inf")
        before = (result.verdict, result.risk_level)
        apply_s_only(result, self.model(), "known")
        self.assertEqual((result.verdict, result.risk_level), before)
        self.assertEqual(result.details["s_only_correction"]["reason_code"], "input_unavailable")
        self.assertEqual(result.details["s_only_correction"]["status"], "unchanged")

    def test_repeated_application_is_idempotent(self):
        result, model = analysis_result(), self.model()
        apply_s_only(result, model, "known")
        once = copy.deepcopy(result)
        apply_s_only(result, model, "known")
        self.assertEqual(result, once)

    def test_malformed_tree_and_cycles_are_rejected(self):
        broken = artifact()
        broken["trees"][0]["children_left"] = [0]
        broken["trees"][0]["children_right"] = [0]
        broken["trees"][0]["feature"] = [0]
        malformed = artifact()
        malformed["trees"][0]["value"] = [[0.1, 0.9]]
        for payload in (broken, malformed):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.model(payload=payload)

    def test_env_loader_default_off_and_explicit_missing_model_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(load_s_only_predictor())
        with patch.dict(os.environ, {"FIDES_S_ONLY_ENABLED": "0", "FIDES_S_ONLY_MODEL": str(self.path)}):
            self.assertIsNone(load_s_only_predictor())
        with patch.dict(os.environ, {"FIDES_S_ONLY_ENABLED": "1", "FIDES_S_ONLY_MODEL": str(self.path)}):
            with self.assertRaises(FileNotFoundError):
                load_s_only_predictor()
        with patch.dict(os.environ, {"FIDES_S_ONLY_ENABLED": "invalid"}):
            with self.assertRaises(ValueError):
                load_s_only_predictor()

    def test_env_loader_accepts_valid_artifact_and_rejects_ontology_mismatch(self):
        self.model()
        environment = {"FIDES_S_ONLY_ENABLED": "1", "FIDES_S_ONLY_MODEL": str(self.path)}
        with patch.dict(os.environ, environment):
            self.assertIsInstance(load_s_only_predictor(), PortableSOnlyModel)
        payload = artifact()
        payload["metadata"]["ontology_sha256"] = "0" * 64
        self.model(payload=payload)
        with patch.dict(os.environ, environment), self.assertRaises(ValueError):
            load_s_only_predictor()

    def test_injected_model_runs_through_actual_engine_and_consistent_final_log(self):
        root = Path(__file__).resolve().parents[1]
        with redirect_stdout(io.StringIO()):
            from analysis_engine import OntologyAnalysisEngine
            engine = OntologyAnalysisEngine(str(root / "ontology"), s_only_predictor=self.model())
            result = engine.analyze([], product_type="known")
        self.assertEqual(verdict_label(result.verdict), "suspicious")
        self.assertEqual(result.details["s_only_correction"]["reason_code"], "corrected_to_s")
        self.assertEqual(result.details["dynamic_weight_log"]["verdict"], result.verdict)
        self.assertEqual(result.details["dynamic_weight_log"]["risk_level"], result.risk_level)


if __name__ == "__main__":
    unittest.main()
