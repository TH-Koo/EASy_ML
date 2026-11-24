import unittest
from unittest.mock import patch

from logic import api


class KonepsQueryDedupTests(unittest.TestCase):
    def test_same_interval_not_downloaded_again_for_each_alias(self):
        class Response:
            status_code = 200
            def json(self):
                return {'response':{'body':{'items':[]}}}
        with patch.object(api, 'COMMON_DATAGO_KEY', 'key'), \
             patch.object(api.requests, 'get', return_value=Response()) as get:
            result = api.verify_koneps(['삼성전자','삼성','SAMSUNG'])
        self.assertEqual(get.call_count, 2)
        self.assertIsNone(result['evidence'])

    def test_failed_interval_is_not_retried_for_every_alias(self):
        with patch.object(api, 'COMMON_DATAGO_KEY', 'key'), \
             patch.object(api.requests, 'get', side_effect=api.requests.ConnectionError('unavailable')) as get:
            api.verify_koneps(['삼성전자','삼성','SAMSUNG'])
        self.assertEqual(get.call_count, 2)


if __name__ == '__main__':
    unittest.main()
