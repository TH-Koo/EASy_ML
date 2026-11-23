from pathlib import Path
import unittest

from analysis_engine import OntologyAnalysisEngine, normalize_text


class SpeechPlatformClaimTests(unittest.TestCase):
    def setUp(self):
        self.engine = OntologyAnalysisEngine(str(Path(__file__).resolve().parents[1] / 'ontology'))

    def speech(self, text):
        return self.engine._score_one_capability('CAP_SPEECH_RECOGNITION', [], normalize_text(text))

    def test_platform_claim_stays_visible_without_implementation_evidence(self):
        for label in ['음성인식플랫폼', '음성 인식 플랫폼', '음성인식 플랫폼', '음성 인식\n플랫폼']:
            with self.subTest(label=label):
                result = self.speech(label + ': Siri, 구글 어시스턴트 지원')
                # Keep the advertised feature visible. A platform label by
                # itself must not supply any implementation evidence.
                self.assertTrue(result.positive_claim)
                self.assertTrue(result.matched_strong_patterns)
                self.assertEqual(result.required_fulfillment_ratio, 0.0)
                self.assertEqual(result.supporting_sources, [])

    def test_independent_speech_claim_is_kept_with_platform_label(self):
        result = self.speech('음성 인식: 지원 / 음성 인식 플랫폼: Siri')
        self.assertTrue(result.positive_claim)
        self.assertIn('음성 인식', result.matched_strong_patterns)

    def test_voice_capable_device_claim_is_kept(self):
        self.assertTrue(self.speech('AI 로봇청소기 음성인식 지원').positive_claim)


if __name__ == '__main__':
    unittest.main()
