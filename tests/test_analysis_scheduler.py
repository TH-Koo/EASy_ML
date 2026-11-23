import threading
import unittest

from logic.analysis_scheduler import AnalysisScheduler, AnalysisQueueFull


class AnalysisSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tasks = {}
        self.scheduler = AnalysisScheduler(self.tasks, max_workers=1, max_pending=2)
        self.release = threading.Event()
        self.started = threading.Event()
        self.running = []

    def tearDown(self):
        self.release.set()
        self.scheduler.shutdown()

    def runner(self, ident, url, owner):
        self.running.append(ident)
        self.started.set()
        self.release.wait(3)
        self.tasks[ident]['done'] = True

    def test_same_product_reuses_job_despite_tracking_parameters(self):
        ident, reused = self.scheduler.submit('https://prod.danawa.com/info/?pcode=123', None, self.runner)
        self.assertTrue(self.started.wait(1))
        again, reused = self.scheduler.submit('https://prod.danawa.com/info/?pcode=123&utm_source=example', None, self.runner)
        self.assertEqual(ident, again)
        self.assertTrue(reused)
        self.assertEqual(len(self.tasks), 1)

    def test_different_products_wait_without_running_another_worker(self):
        first, _ = self.scheduler.submit('https://prod.danawa.com/info/?pcode=1', None, self.runner)
        self.assertTrue(self.started.wait(1))
        second, _ = self.scheduler.submit('https://prod.danawa.com/info/?pcode=2', None, self.runner)
        self.assertTrue(self.tasks[first]['started'])
        self.assertFalse(self.tasks[second]['started'])
        self.assertEqual(self.running, [first])

    def test_results_are_not_shared_between_logged_in_users(self):
        first, _ = self.scheduler.submit('https://prod.danawa.com/info/?pcode=1', 1, self.runner)
        second, reused = self.scheduler.submit('https://prod.danawa.com/info/?pcode=1', 2, self.runner)
        self.assertNotEqual(first, second)
        self.assertFalse(reused)

    def test_bounded_queue_still_accepts_duplicate(self):
        url = 'https://prod.danawa.com/info/?pcode=1'
        first, _ = self.scheduler.submit(url, None, self.runner)
        self.scheduler.submit('https://prod.danawa.com/info/?pcode=2', None, self.runner)
        with self.assertRaises(AnalysisQueueFull):
            self.scheduler.submit('https://prod.danawa.com/info/?pcode=3', None, self.runner)
        self.assertEqual(self.scheduler.submit(url, None, self.runner), (first, True))

    def test_finished_job_can_be_requested_again(self):
        self.release.set()
        url = 'https://prod.danawa.com/info/?pcode=1'
        first, _ = self.scheduler.submit(url, None, self.runner)
        self.assertTrue(self.started.wait(1))
        self.scheduler.shutdown()
        # No runner is required for the already completed job: the next submit
        # must try new work rather than return that old job.
        with self.assertRaises(RuntimeError):
            self.scheduler.submit(url, None, self.runner)
        self.assertEqual(list(self.tasks), [first])  # failed submit leaves no phantom task


if __name__ == '__main__':
    unittest.main()
