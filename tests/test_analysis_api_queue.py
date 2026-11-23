import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import server
from logic.analysis_scheduler import AnalysisScheduler


class AnalysisApiQueueTests(unittest.TestCase):
    def test_post_reuses_job_and_queued_progress_is_truthful(self):
        tasks = {}
        scheduler = AnalysisScheduler(tasks, max_workers=1)
        release, started = threading.Event(), threading.Event()
        def run(ident, url, owner):
            tasks[ident]['events'].append({'type': 'progress', 'step': 1, 'message': '3/6개 구간 완료',
                                          'progress': {'completed': 3, 'total': 6}})
            started.set()
            release.wait(3)
            tasks[ident]['done'] = True
        try:
            with patch.object(server, '_tasks', tasks), \
                 patch.object(server, '_ANALYSIS_SCHEDULER', scheduler), \
                 patch.object(server, 'run_analysis', side_effect=run), \
                 TestClient(server.app) as client:
                first = client.post('/api/analyze', json={'url': 'https://prod.danawa.com/info/?pcode=1'})
                self.assertEqual(first.status_code, 202)
                self.assertTrue(started.wait(1))
                first_id = first.json()['analysis_id']
                duplicate = client.post('/api/analyze', json={'url': 'https://prod.danawa.com/info/?pcode=1&utm_source=test'})
                self.assertEqual(duplicate.json()['analysis_id'], first_id)
                self.assertTrue(duplicate.json()['reused'])
                another = client.post('/api/analyze', json={'url': 'https://prod.danawa.com/info/?pcode=2'})
                queued = client.get('/api/analyze/' + another.json()['analysis_id'] + '/progress').json()
                self.assertEqual(queued['status'], 'queued')
                self.assertIsNone(queued['current_stage'])
                progress = client.get('/api/analyze/' + first_id + '/progress').json()
                self.assertEqual(progress['status'], 'running')
                self.assertEqual(progress['stages'][1]['sub_label'], '3/6개 구간 완료')
                self.assertEqual(len(tasks), 2)
        finally:
            release.set()
            scheduler.shutdown()


if __name__ == '__main__':
    unittest.main()
