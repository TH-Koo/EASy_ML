import copy
import json
import unittest

from server import build_analysis_result, claims_from_result_json


class AdvertisedClaimDisplayTests(unittest.TestCase):
    def payload(self, specs=None, capabilities=None):
        return {'product_name':'몬스타 서머너 버즈 AI', '_category':'무선 이어폰',
                'specs':specs if specs is not None else [{'key':'음성인식플랫폼','value':'지원'}, {'key':'Siri','value':'○'}],
                'capability_scores':capabilities or [],
                'ontology_scores':{'accs':4,'hes':0,'tes':0,'ces':0,'ecs':0,'conf':0},
                'ontology_verdict':'AI 워싱 상품 / Washing',
                's_only_correction':{'model_version':'unchanged-model'}}

    def test_platform_feature_replaces_generic_ai_name_claim(self):
        result = build_analysis_result('ad', self.payload())
        self.assertEqual(result['product']['ai_claims_count'],1)
        claim = result['claims'][0]
        self.assertEqual(claim['id'],'CAP_SPEECH_RECOGNITION')
        self.assertEqual(claim['text'],'음성 인식')
        self.assertEqual(claim['status'],'unsupported')
        self.assertIn('충분하지',claim['explanation']['result'])
        self.assertEqual(claim['evidence'][0]['source'],'seller_page')

    def test_display_does_not_change_scores_model_or_saved_payload(self):
        payload = self.payload()
        original = copy.deepcopy(payload)
        result = build_analysis_result('ad', payload)
        self.assertEqual(payload, original)
        self.assertEqual(result['scores']['overall_raw'],4)
        self.assertEqual(result['s_only_correction'],original['s_only_correction'])
        self.assertEqual(claims_from_result_json(json.dumps(payload)),result['claims'])

    def test_supported_native_speech_keeps_engine_evidence_status(self):
        cap = {'capability_id':'CAP_SPEECH_RECOGNITION','capability_name_ko':'음성 인식',
               'positive_claim':True,'required_fulfillment_ratio':0.9,'supporting_sources':['kipris']}
        result = build_analysis_result('native',self.payload({'음성인식':'○','음성인식플랫폼':'지원'},[cap]))
        self.assertEqual(result['claims'][0]['status'],'verified')
        self.assertNotIn('explanation',result['claims'][0])

    def test_unavailable_platform_does_not_invent_a_voice_claim(self):
        result = build_analysis_result('none',self.payload({'음성인식플랫폼':'×'}))
        self.assertEqual([row['id'] for row in result['claims']],['PRODUCT_NAME_AI'])

    def test_filtered_advertised_feature_is_visible_but_unverified(self):
        cap = {'capability_id':'CAP_SPEECH_RECOGNITION','capability_name_ko':'음성 인식',
               'positive_claim':False,'matched_strong_patterns':['음성인식']}
        result = build_analysis_result('filtered',self.payload({},[cap]))
        self.assertEqual(result['claims'][0]['id'],'CAP_SPEECH_RECOGNITION')
        self.assertEqual(result['claims'][0]['status'],'unsupported')

    def test_unrelated_category_and_unadvertised_capabilities_stay_hidden(self):
        caps = [{'capability_id':'CAP_DRY_COURSE','positive_claim':False,
                 'matched_strong_patterns':['건조 코스']},
                {'capability_id':'CAP_OBJECT_DETECTION','positive_claim':False,
                 'matched_strong_patterns':[]}]
        result = build_analysis_result('unrelated',self.payload({},caps))
        self.assertEqual([row['id'] for row in result['claims']],['PRODUCT_NAME_AI'])


if __name__ == '__main__':
    unittest.main()
