import io
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
import logic.crawler as crawler


def image_response(height):
    stream = io.BytesIO()
    Image.new('RGB', (860, height), 'white').save(stream, format='PNG')
    class Response:
        content = stream.getvalue()
        def raise_for_status(self):
            pass
    return Response()


class CrawlerImageLimitTests(unittest.TestCase):
    def test_single_tall_image_cannot_bypass_limit(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(crawler, 'DETAIL_MAX_HEIGHT', 1200):
            target = os.path.join(directory, 'detail.png')
            with patch('requests.get', return_value=image_response(6400)) as get:
                crawler._stitch_detail_images(['https://images/first', 'https://images/second'], target, 'https://prod.danawa.com')
            with Image.open(target) as image:
                self.assertEqual(image.size, (860, 1200))
            self.assertEqual(get.call_count, 1)

    def test_second_image_is_cropped_to_remaining_height(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(crawler, 'DETAIL_MAX_HEIGHT', 1200):
            target = os.path.join(directory, 'detail.png')
            with patch('requests.get', side_effect=[image_response(800), image_response(800)]):
                crawler._stitch_detail_images(['https://images/first', 'https://images/second'], target, 'https://prod.danawa.com')
            with Image.open(target) as image:
                self.assertEqual(image.height, 1200)

    @patch.dict(os.environ, {'EASY_DETAIL_MODE': 'images'})
    def test_old_oversized_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(crawler, 'DETAIL_MAX_HEIGHT', 1200):
            target = os.path.join(directory, 'detail.png')
            Image.new('RGB', (860, 2000)).save(target)
            cached = {'url': 'https://prod.danawa.com', 'created_at': time.time(),
                      'screenshot_path': target, 'detail_max_height': 1200}
            self.assertFalse(crawler._is_cache_valid(cached, cached['url']))
            Image.new('RGB', (860, 1200)).save(target)
            self.assertTrue(crawler._is_cache_valid(cached, cached['url']))
            del cached['detail_max_height']
            self.assertFalse(crawler._is_cache_valid(cached, cached['url']))


if __name__ == '__main__':
    unittest.main()
