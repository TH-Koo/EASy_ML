import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from logic.evidence_cache import query_cached


class EvidenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'EASY_EVIDENCE_CACHE_DIR': self.directory.name,
                                           'EASY_EVIDENCE_CACHE_SECONDS': '300'})
        self.env.start()
        self.calls = 0

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def provider(self, company, model):
        self.calls += 1
        return {'records': [{'title': f'{company}:{model}'}]}

    def test_same_query_reuses_data_without_shared_mutable_results(self):
        query_cached('RRA', self.provider, 'A', 'M1')['records'].clear()
        result = query_cached('RRA', self.provider, 'A', 'M1')
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(self.calls, 1)

    def test_company_model_provider_and_revision_are_distinct(self):
        for provider, company, model, revision in [('RRA','A','M1',''), ('RRA','B','M1',''),
                                                  ('RRA','A','M2',''), ('TTA','A','M1',''),
                                                  ('RRA','A','M1','v2')]:
            query_cached(provider, self.provider, company, model, revision=revision)
        self.assertEqual(self.calls, 5)

    def test_expired_or_corrupt_cache_is_refetched(self):
        query_cached('RRA', self.provider, 'A', 'M1')
        path = next(Path(self.directory.name).glob('*.json'))
        saved = json.loads(path.read_text(encoding='utf-8'))
        saved['saved_at'] -= 301
        path.write_text(json.dumps(saved), encoding='utf-8')
        query_cached('RRA', self.provider, 'A', 'M1')
        path.write_text('{broken', encoding='utf-8')
        query_cached('RRA', self.provider, 'A', 'M1')
        self.assertEqual(self.calls, 3)

    def test_errors_empty_and_partial_results_are_not_cached(self):
        for result in [{'error':'failure'}, {'records':[]},
                       {'records':[{'title':'partial'}], 'collection_partial':True},
                       {'status':'조회 불가', 'records':[{'title':'invalid'}]}]:
            def fetch():
                self.calls += 1
                return result
            query_cached('test', fetch)
            query_cached('test', fetch)
        self.assertEqual(self.calls, 8)

    def test_disabled_cache_does_not_read_or_write(self):
        query_cached('RRA', self.provider, 'A', 'M1')
        with patch.dict(os.environ, {'EASY_EVIDENCE_CACHE_SECONDS':'0'}):
            query_cached('RRA', self.provider, 'A', 'M1')
            query_cached('RRA', self.provider, 'A', 'M1')
        self.assertEqual(self.calls, 3)

    def test_concurrent_identical_queries_fetch_once(self):
        barrier = threading.Barrier(2)
        def fetch(company):
            self.calls += 1
            time.sleep(0.03)
            return {'records':[{'title':company}]}
        def request():
            barrier.wait()
            return query_cached('test', fetch, 'A')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: request(), range(2)))
        self.assertEqual(first, second)
        self.assertEqual(self.calls, 1)


if __name__ == '__main__':
    unittest.main()
