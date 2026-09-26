"""Numerical, leakage and existing-engine integration checks (stdlib unittest)."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
import torch

from fides_ml.data import connected_groups, group_split, load_training_frame
from fides_ml.demo import make_demo
from fides_ml.evaluate import score_labels
from fides_ml.features import CONTEXT_COLUMNS, FeatureEncoder, feature_row, normalize_label, read_csv, score_bundle
from fides_ml.model import CENWeightModel, ModelConfig
from fides_ml.objective import CENSENN, ordinal_log_probs, senn_penalty
from fides_ml.predict import WeightPredictor
from fides_ml.prepare import prepare_dataset
from fides_ml.train import TrainConfig, train_model


class NumericalTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(3)
        torch.set_num_threads(2)
        self.model = CENSENN(ModelConfig(category_dim=2))
        self.h = torch.tensor([[.2, .7, .9], [.0, .5, .8]])
        self.c = torch.rand(2, len(CONTEXT_COLUMNS))
        self.cat = torch.eye(2)
        self.mask = torch.tensor([[1., 1., 0.], [1., 1., 1.]])
        self.ecs = torch.tensor([.4, .6])

    def test_masks_reconstruction_and_observed_zero(self):
        out = self.model(self.h, self.c, self.cat, self.mask, self.ecs)
        torch.testing.assert_close(out["weights"].sum(-1), torch.ones(2))
        self.assertEqual(float(out["weights"][0, 2].detach()), 0)
        self.assertGreater(float(out["weights"][1, 0].detach()), 0)  # Measured 0 is not missing.
        torch.testing.assert_close(out["accs"], out["accs_contributions"].sum(-1) + out["ecs_contribution"])

    def test_missing_nan_has_no_effect(self):
        normal = self.model(self.h, self.c, self.cat, self.mask, self.ecs)
        changed = self.h.clone()
        changed[0, 2] = float("nan")
        out = self.model(changed, self.c, self.cat, self.mask, self.ecs)
        torch.testing.assert_close(normal["accs"], out["accs"])

    def test_all_missing_does_not_create_nan(self):
        out = self.model(self.h, self.c, self.cat, torch.zeros_like(self.mask), self.ecs)
        self.assertFalse(out["valid"].any())
        self.assertTrue(torch.isfinite(out["accs"]).all())
        self.assertEqual(float(out["weights"].sum().detach()), 0)

    def test_ecs_is_fixed_blend_not_gate_input(self):
        a = self.model(self.h, self.c, self.cat, self.mask, torch.zeros(2))
        b = self.model(self.h, self.c, self.cat, self.mask, torch.ones(2))
        torch.testing.assert_close(a["weights"], b["weights"])
        torch.testing.assert_close(b["accs"] - a["accs"], torch.full((2,), 15.))

    def test_concept_intervention_has_exact_positive_effect(self):
        a = self.model(self.h, self.c, self.cat, self.mask, self.ecs)
        changed = self.h.clone()
        changed[:, 0] += .01
        b = self.model(changed, self.c, self.cat, self.mask, self.ecs)
        torch.testing.assert_close(a["weights"], b["weights"])
        torch.testing.assert_close(b["accs"] - a["accs"], .85 * a["weights"][:, 0], atol=1e-5, rtol=1e-4)

    def test_senn_uses_context_and_backpropagates_second_derivatives(self):
        h, c = self.h.clone().requires_grad_(), self.c.clone().requires_grad_()
        out = self.model(h, c, self.cat, self.mask, self.ecs)
        penalty = senn_penalty(out, h, c)
        self.assertGreater(float(penalty.detach()), 0)
        penalty.backward()
        self.assertGreater(sum(float(p.grad.abs().sum()) for p in self.model.gate.parameters() if p.grad is not None), 0)
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in self.model.gate.parameters() if p.grad is not None))

    def test_context_gradient_matches_finite_difference(self):
        c = self.c.double().requires_grad_()
        model = self.model.double()
        args = (self.h.double(), c, self.cat.double(), self.mask.double(), self.ecs.double())
        out = model(*args)
        grad = torch.autograd.grad(out["score"].sum(), c)[0]
        eps = 1e-5
        plus, minus = c.detach().clone(), c.detach().clone()
        plus[0, 0] += eps
        minus[0, 0] -= eps
        fplus = model(args[0], plus, *args[2:])["score"][0]
        fminus = model(args[0], minus, *args[2:])["score"][0]
        self.assertAlmostEqual(float(grad[0, 0]), float(((fplus-fminus)/(2*eps)).detach()), places=8)

    def test_ordinal_probabilities_and_boundary_semantics(self):
        cfg = self.model.config
        score = torch.tensor([0., 21.8, 28., 35., 100.], requires_grad=True)
        logs = ordinal_log_probs(score, cfg)
        torch.testing.assert_close(logs.exp().sum(-1), torch.ones(5))
        self.assertEqual(score_labels(score.detach().numpy(), cfg).tolist(), [0, 1, 1, 2, 2])
        (-logs[:, 1].mean()).backward()
        self.assertTrue(torch.isfinite(score.grad).all())

    def test_config_rejects_invalid_cutoffs(self):
        with self.assertRaises(ValueError):
            ModelConfig(category_dim=2, washing_cutoff=50, genuine_cutoff=30)


class DataTests(unittest.TestCase):
    def test_suspicious_remains_an_ordinal_target(self):
        self.assertEqual(normalize_label("Suspicious"), "suspicious")
        self.assertEqual(normalize_label("Genuine"), "genuine")
        self.assertIsNone(normalize_label("Insufficient"))
        with self.assertRaises(ValueError):
            normalize_label("arbitrary")

    def test_group_union_prevents_cross_column_family_leakage(self):
        frame = pd.DataFrame([
            {"sample_id": "1", "split_group": "A", "base_model_id": "M1"},
            {"sample_id": "2", "split_group": "B", "base_model_id": "M1"},
            {"sample_id": "3", "split_group": "B", "base_model_id": "M2"},
            {"sample_id": "4", "split_group": "C", "base_model_id": "M3"},
        ])
        groups = connected_groups(frame.fillna(""))
        self.assertEqual(len(set(groups[:3])), 1)
        self.assertNotEqual(groups[0], groups[3])

    def test_missing_groups_fail_instead_of_row_split(self):
        with self.assertRaises(ValueError):
            connected_groups(pd.DataFrame([{"sample_id": "1", "product_name": "product"}]))

    def test_split_is_deterministic_and_vocabulary_train_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"data.csv"
            make_demo(path, n_groups=45)
            frame, _ = load_training_frame(path)
            split = group_split(frame)
            again = group_split(frame)
            for k in split:
                np.testing.assert_array_equal(split[k], again[k])
                self.assertEqual(set(frame.iloc[split[k]].target), {0, 1, 2})
            self.assertFalse(set(frame.iloc[split["train"]].group_id) & set(frame.iloc[split["test"]].group_id))
            encoder = FeatureEncoder().fit(frame.iloc[split["train"]])
            changed = frame.iloc[:1].copy()
            changed["product_type"] = "new_category"
            self.assertEqual(float(encoder.transform(changed)[2][0].sum()), 0.0)

    def test_invalid_active_score_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"data.csv"
            make_demo(path, n_groups=9)
            frame = read_csv(path)
            frame.loc[0, "hes"] = "missing"
            with self.assertRaises(ValueError):
                FeatureEncoder().fit(frame).transform(frame)

    def test_real_engine_contract_and_label_reason_exclusion(self):
        from analysis_engine import OntologyAnalysisEngine
        root = Path(__file__).resolve().parents[1]
        engine = OntologyAnalysisEngine(str(root/"ontology"))
        result = score_bundle({"product_json": {"product_name": "AI 로봇청소기", "raw_specs": "AI 사물인식 카메라 장애물 회피"}}, engine)
        before = feature_row(result, sample_id="test", product_type="로봇청소기")
        result.details["matched_patterns"] = "strict-negative washing ground truth"
        result.verdict = "FAKE LABEL DO NOT READ"
        after = feature_row(result, sample_id="test", product_type="로봇청소기")
        self.assertEqual(before, after)
        self.assertEqual(set(c for c in before if c.startswith("ctx_")), set(CONTEXT_COLUMNS))

    def test_prepare_retains_three_labels(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(__file__).resolve().parents[1]
            labels = pd.DataFrame([{ "url": f"https://example.invalid/{i}", "label": label,
                "product_name": f"AI 로봇청소기 {i}", "specs_text": "AI 사물인식 장애물 회피",
                "product_type": "로봇청소기", "base_model_id": str(i)}
                for i, label in enumerate(["washing", "suspicious", "genuine"])])
            source, output = Path(d)/"labels.csv", Path(d)/"features.csv"
            labels.to_csv(source, index=False)
            report = prepare_dataset(source, output, seller_only=True, ontology_dir=root/"ontology")
            self.assertEqual(report["prepared_rows"], 3)
            self.assertEqual(set(read_csv(output).label), {"washing", "suspicious", "genuine"})


class EndToEndTests(unittest.TestCase):
    def test_train_save_reload_inference_and_abstention(self):
        with tempfile.TemporaryDirectory() as d:
            source, output = Path(d)/"data.csv", Path(d)/"run"
            make_demo(source, n_groups=36)
            report = train_model(source, output, train_config=TrainConfig(epochs=4, patience=3))
            predictor = WeightPredictor(output)
            saved = pd.read_csv(output/"test_predictions.csv")
            features = read_csv(source).set_index("sample_id").loc[saved.sample_id].reset_index()
            predicted = predictor.predict_frame(features)
            for c in ("hes", "tes", "ces"):
                np.testing.assert_allclose(predicted[f"weight_{c}"], saved[f"weight_{c}"], atol=1e-6)
            self.assertNotIn("accs", predicted)
            self.assertNotIn("predicted_label", predicted)
            self.assertLess(report["explanation_checks"]["max_accs_reconstruction_error"], 1e-4)
            absent = features.iloc[:1].copy()
            for c in ("hes", "tes", "ces"):
                absent[f"mask_{c}"] = "0"
                absent[c] = ""
            result = predictor.predict_frame(absent)
            self.assertEqual(result.iloc[0].status, "no_usable_channels")
            self.assertEqual(float(result.filter(like="weight_").sum(axis=1).iloc[0]), 0)
            # An existing run must never be silently overwritten.
            with self.assertRaises(ValueError):
                train_model(source, output, train_config=TrainConfig(epochs=1))


class WeightModuleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(__file__).resolve().parents[1]
        cls.path = Path(cls.temp.name)
        make_demo(cls.path/"features.csv", n_groups=12)
        frame = read_csv(cls.path/"features.csv")
        encoder = FeatureEncoder().fit(frame)
        cfg = ModelConfig(category_dim=encoder.category_dim)
        torch.manual_seed(5)
        model = CENSENN(cfg)
        torch.save(model.state_dict(), cls.path/"model.pt")
        # Actual v1 format: loading this needs no parameter migration.
        (cls.path/"metadata.json").write_text(json.dumps({
            "format_version": 1, "model_config": cfg.to_dict(),
            "encoder": encoder.to_dict(), "labels": ["washing", "suspicious", "genuine"]}), encoding="utf-8")
        cls.predictor = WeightPredictor(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _analysis(self, predictor=None):
        from fides_integration import secure_analyze_bundle
        return secure_analyze_bundle(
            product_json={"product_name": "AI 로봇청소기", "raw_specs": "AI 카메라 사물인식 장애물 회피", "category": "로봇청소기"},
            ontology_dir=str(self.root/"ontology"), weight_predictor=predictor)

    def test_weight_serving_requires_no_ecs_or_label(self):
        frame = read_csv(self.path/"features.csv").drop(columns=["ecs", "label"])
        result = self.predictor.predict_frame(frame)
        self.assertTrue(result.status.eq("ok").all())
        self.assertNotIn("accs", result)
        self.assertNotIn("risk_band", result)

    def test_generator_forward_has_only_weights_and_validity(self):
        frame = read_csv(self.path/"features.csv").head(2)
        tensors = [torch.tensor(a) for a in self.predictor.encoder.transform_weights(frame)]
        self.assertEqual(set(self.predictor.model(*tensors)), {"weights", "valid"})

    def test_v1_weights_equal_training_wrapper(self):
        frame = read_csv(self.path/"features.csv").head(3)
        objective = CENSENN(self.predictor.config)
        objective.load_state_dict(self.predictor.model.state_dict(), strict=True)
        arrays = self.predictor.encoder.transform(frame)
        trained = objective(*(torch.tensor(a) for a in arrays))
        served = self.predictor.predict_frame(frame)
        np.testing.assert_allclose(trained["weights"].detach().numpy(), served.filter(like="weight_").to_numpy(), atol=1e-6)

    def test_engine_and_training_accs_match_and_logs_are_consistent(self):
        from fides_integration import result_consistency_errors
        result = self._analysis(self.predictor)
        frame = pd.DataFrame([feature_row(result, sample_id="test", product_type="로봇청소기")])
        objective = CENSENN(self.predictor.config)
        objective.load_state_dict(self.predictor.model.state_dict())
        values = objective(*(torch.tensor(a) for a in self.predictor.encoder.transform(frame)))
        actual = result.details["dynamic_weighting"]
        self.assertAlmostEqual(float(values["accs"][0].detach()), actual["unrounded_accs"], places=4)
        self.assertEqual(round(actual["unrounded_accs"], 2), result.accs)
        self.assertAlmostEqual(sum(actual["contributions"].values()), actual["unrounded_accs"], places=7)
        self.assertEqual(result.raw_accs, actual["dynamic_evidence_score"])
        self.assertEqual(result_consistency_errors(result), [])
        self.assertEqual(actual["model_version"], self.predictor.model_version)
        self.assertIn("학습 모델", " ".join(result.reasons))

    def test_provider_called_once_before_final_result_and_cannot_override_it(self):
        class Spy:
            calls = []
            def predict_weights(inner, **kwargs):
                inner.calls.append(kwargs)
                active = [c for c, ok in kwargs["channel_mask"].items() if ok]
                return {"weights": {c: 1/len(active) if c in active else 0 for c in ("hes", "tes", "ces")},
                        "method": "test", "model_version": "test", "accs": 999, "verdict": "FAKE"}
        spy = Spy()
        result = self._analysis(spy)
        self.assertEqual(len(spy.calls), 1)
        self.assertEqual(set(spy.calls[0]), {"channel_scores", "channel_details", "product_type", "channel_mask"})
        self.assertEqual(spy.calls[0]["product_type"], "로봇청소기")
        self.assertLessEqual(result.accs, 100)
        self.assertNotEqual(result.verdict, "FAKE")

    def test_engine_still_applies_confidence_and_claim_rules(self):
        from analysis_engine import OntologyAnalysisEngine
        engine = OntologyAnalysisEngine(str(self.root/"ontology"), weight_predictor=self.predictor)
        verdict, _ = engine._decide_verdict(accs=10, confidence=40, sufficiency=0, positive_caps=[object()])
        self.assertIn("Suspected", verdict)
        verdict, _ = engine._decide_verdict(accs=90, confidence=90, sufficiency=1, positive_caps=[])
        self.assertIn("Not Evaluated", verdict)

    def test_all_missing_is_reported_but_engine_owns_decision(self):
        from analysis_engine import OntologyAnalysisEngine
        engine = OntologyAnalysisEngine(str(self.root/"ontology"), weight_predictor=self.predictor)
        result = engine.analyze([])
        dynamic = result.details["dynamic_weighting"]
        self.assertEqual(dynamic["weight_status"], "no_usable_channels")
        self.assertEqual(sum(dynamic["weights"].values()), 0)
        self.assertIn("Not Evaluated", result.verdict)

    def test_training_and_engine_configuration_drift_fails(self):
        from dataclasses import replace
        from fides_config import DEFAULT_ENGINE_CONFIG
        from analysis_engine import OntologyAnalysisEngine
        cfg = replace(DEFAULT_ENGINE_CONFIG, thresholds=replace(DEFAULT_ENGINE_CONFIG.thresholds, normal=60))
        with self.assertRaisesRegex(ValueError, "scoring settings differ"):
            OntologyAnalysisEngine(str(self.root/"ontology"), weight_predictor=self.predictor, engine_config=cfg)
        with self.assertRaisesRegex(ValueError, "enable_dynamic"):
            OntologyAnalysisEngine(str(self.root/"ontology"), weight_predictor=self.predictor, enable_dynamic_weighting=False)

    def test_invalid_weights_are_rejected_by_engine(self):
        from analysis_engine import OntologyAnalysisEngine
        class Broken:
            def predict_weights(self, **kwargs):
                return {"weights": {"hes": float("nan"), "tes": .5, "ces": .5}}
        with self.assertRaisesRegex(ValueError, "finite"):
            self._analysis(Broken())
        class MissingChannel:
            def predict_weights(self, **kwargs):
                return {"weights": {"hes": .25, "tes": .25, "ces": .5}}
        engine = OntologyAnalysisEngine(str(self.root/"ontology"), weight_predictor=MissingChannel())
        with self.assertRaisesRegex(ValueError, "Missing channels"):
            engine._calculate_dynamic_weighting(40, 25, 0, 10, {c: {} for c in ("hes", "tes", "ces")})

    def test_shared_formula_example_and_tensor_gradients(self):
        from fides_scoring import calculate_accs
        weights = {"hes": .2, "tes": .5, "ces": .3}
        plain = calculate_accs({"hes": 40, "tes": 25, "ces": 20}, weights, 10)
        self.assertAlmostEqual(plain["accs"], 24.025)
        h = torch.tensor([40., 25., 20.], requires_grad=True)
        differentiable = calculate_accs(dict(zip(("hes", "tes", "ces"), h)), weights, 10.)
        differentiable["accs"].backward()
        torch.testing.assert_close(h.grad, torch.tensor([.17, .425, .255]))


if __name__ == "__main__":
    unittest.main()
