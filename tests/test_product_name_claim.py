import json
import unittest

from server import build_analysis_result, claims_from_result_json


class ProductNameClaimTests(unittest.TestCase):
    def test_name_only_claim_has_same_count_in_result_and_history(self):
        payload = {'product_name':'AI 이어폰', 'capability_scores':[],
                   'ontology_reasons':['구체적인 기능 미확인', '공공 기록 미확인']}
        result = build_analysis_result('name-only', payload)
        history_claims = claims_from_result_json(json.dumps(payload))
        self.assertEqual(result['product']['ai_claims_count'], 1)
        self.assertEqual(result['claims'], history_claims)
        self.assertEqual(result['claims'][0]['id'], 'PRODUCT_NAME_AI')
        self.assertEqual(result['claims'][0]['status'], 'unsupported')
        self.assertEqual(result['claims'][0]['evidence'], [])

    def test_no_ai_claim_does_not_count_analysis_reason_sentences(self):
        result = build_analysis_result('ordinary', {
            'product_name':'일반 이어폰', 'capability_scores':[],
            'ontology_reasons':['설명 하나', '설명 둘'],
        })
        self.assertEqual(result['product']['ai_claims_count'], 0)
        self.assertEqual(result['claims'], [])

    def test_count_includes_all_claims_instead_of_only_top_five(self):
        capabilities = [{'capability_id':f'cap-{i}', 'capability_name_ko':f'기능 {i}',
                         'positive_claim':True} for i in range(7)]
        result = build_analysis_result('seven', {
            'product_name':'AI 제품', 'capability_scores':capabilities,
            'top_capabilities':capabilities[:5],
        })
        self.assertEqual(result['product']['ai_claims_count'], 7)
        self.assertEqual(len(result['claims']), 7)


if __name__ == '__main__':
    unittest.main()
