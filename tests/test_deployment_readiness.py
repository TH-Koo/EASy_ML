import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import URLError

from scripts.check_deployment import probe_services, wait_for_services


class DeploymentReadinessTests(unittest.TestCase):
    def test_frontend_success_does_not_hide_backend_connection_failure(self):
        frontend = unittest.mock.MagicMock()
        frontend.__enter__.return_value.status = 200
        with patch('scripts.check_deployment.urlopen', side_effect=[frontend, URLError('refused')]):
            failures = probe_services('http://frontend', 'http://backend')
        self.assertEqual(len(failures), 1)
        self.assertIn('backend', failures[0])

    def test_other_http_service_is_not_a_healthy_analysis_api(self):
        frontend = unittest.mock.MagicMock()
        frontend.__enter__.return_value.status = 200
        backend = unittest.mock.MagicMock()
        backend.__enter__.return_value.read.return_value = b'{"paths": {}}'
        with patch('scripts.check_deployment.urlopen', side_effect=[frontend, backend]):
            failures = probe_services('http://frontend', 'http://backend')
        self.assertTrue(any('/api/analyze' in failure for failure in failures))

    def test_short_lived_backend_is_not_reported_ready(self):
        with patch('scripts.check_deployment.probe_services', side_effect=[[], [], ['backend refused']]), \
             patch('scripts.check_deployment.time.monotonic', side_effect=[0, 0, 1, 2]), \
             patch('scripts.check_deployment.time.sleep'), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'backend refused'):
                wait_for_services('http://frontend', 'http://backend', timeout=2)

    def test_backend_can_finish_startup_before_readiness_passes(self):
        with patch('scripts.check_deployment.probe_services', side_effect=[['starting'], [], [], []]), \
             patch('scripts.check_deployment.time.monotonic', return_value=0), \
             patch('scripts.check_deployment.time.sleep'), redirect_stdout(io.StringIO()):
            wait_for_services('http://frontend', 'http://backend')


if __name__ == '__main__':
    unittest.main()
