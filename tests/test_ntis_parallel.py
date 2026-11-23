import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import logic.api as api


class NtisParallelTests(unittest.TestCase):
    def test_queries_and_pages_overlap_but_http_concurrency_is_bounded(self):
        lock = threading.Lock()
        active = maximum = 0
        def get(url, params=None, timeout=None):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(0.025)
                query, pos = params['SRWR'], params['startPosition']
                hit = (f'<HIT><ProjectNumber>{query}-{pos}</ProjectNumber>'
                       f'<ProjectTitle><Korean>{query}-{pos} 인공지능 연구</Korean></ProjectTitle>'
                       '<ResearchAgency><Name>삼성전자</Name></ResearchAgency></HIT>')
                class Response:
                    status_code = 200
                    text = f'<RESULT><TOTALHITS>101</TOTALHITS>{hit}</RESULT>'
                return Response()
            finally:
                with lock:
                    active -= 1
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'EASY_NTIS_CACHE_DIR': directory}), \
             patch.object(api, 'NTIS_API_KEY', 'key'), \
             patch.object(api, '_NTIS_HTTP_SLOTS', threading.BoundedSemaphore(2)), \
             patch.object(api, '_NTIS_WORKERS', 2), \
             patch.object(api.requests, 'get', side_effect=get):
            result = api.verify_ntis_rnd(['삼성전자'])
        self.assertEqual(maximum, 2)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(len(result['records']), 9)  # company first page + four queries x two pages

    def test_parallelism_preserves_record_and_error_order(self):
        def fetch(key, query, cap):
            time.sleep(0.01 if query.endswith('인공지능') else 0)
            return [query], [query + ' error']
        def project(query, company):
            return {'project_name': query, 'project_number': query}
        with patch.object(api, '_ntis_cache_load', return_value=None), \
             patch.object(api, '_ntis_fetch_all', side_effect=fetch), \
             patch.object(api, '_ntis_project_from_hit', side_effect=project):
            with patch.object(api, '_NTIS_WORKERS', 1):
                sequential = api._ntis_projects_for_company('key', '삼성전자')
            with patch.object(api, '_NTIS_WORKERS', 2):
                parallel = api._ntis_projects_for_company('key', '삼성전자')
        self.assertEqual(parallel, sequential)
        self.assertEqual(len(parallel[0]), 5)


if __name__ == '__main__':
    unittest.main()
