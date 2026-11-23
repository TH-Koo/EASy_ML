import ast
import os
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

from logic import crawler
from pipeline_main import run_product_ocr


class SpecsOnlyTests(unittest.TestCase):
    def test_specs_flow_never_scrolls_captures_or_runs_ocr(self):
        driver = Mock()
        with patch.dict(os.environ, {'EASY_DETAIL_MODE':'specs'}), \
             patch.object(crawler, '_load_cached_product_data', return_value=None), \
             patch.object(crawler, '_save_cached_product_data'), \
             patch.object(crawler, '_setup_driver', return_value=driver), \
             patch.object(crawler, '_open_product_page'), \
             patch.object(crawler, '_extract_product_title', return_value='삼성전자 세탁기 M123'), \
             patch.object(crawler, '_extract_category', return_value=['세탁기']), \
             patch.object(crawler, '_extract_specs', return_value=({'AI세탁':'○'}, 'AI세탁')), \
             patch.object(crawler, '_click_more_button_if_exists') as click, \
             patch.object(crawler, '_slow_scroll_to_bottom') as scroll, \
             patch.object(crawler, '_capture_detail_area') as capture:
            product = crawler.get_product_data('https://prod.danawa.com/info/?pcode=1')
        click.assert_not_called()
        scroll.assert_not_called()
        capture.assert_not_called()
        self.assertEqual(product['screenshot_path'], '')
        self.assertEqual(product['collection_mode'], 'specs')
        self.assertEqual(run_product_ocr({**product, 'screenshot_path':'old.png'})['reason'], 'specs_only')
        driver.quit.assert_called_once()

    def test_valid_legacy_specs_cache_needs_no_image(self):
        cached = {'url':'https://prod.danawa.com/info/?pcode=1', 'created_at':time.time(),
                  'product_data':{'specs':{'제조회사':'삼성전자','AI세탁':'○'}}}
        with patch.dict(os.environ, {'EASY_DETAIL_MODE':'specs'}):
            self.assertTrue(crawler._is_cache_valid(cached, cached['url']))
            cached['created_at'] -= crawler.CRAWLER_CACHE_TTL_SECONDS + 1
            self.assertFalse(crawler._is_cache_valid(cached, cached['url']))

    def test_old_ocr_and_unrelated_body_are_not_used(self):
        original = {'specs':{'AI세탁':'○','객체감지':'×','화자인식':'미지원','빈칸':''},
                    'raw_specs':'unrelated ads', 'description':'unrelated body',
                    'ocr_text':'old OCR', 'ocr_extracted_text':'old OCR'}
        product = crawler._as_specs_product(original)
        self.assertEqual(product['specs'], {'AI세탁':'○'})
        self.assertEqual(product['raw_specs'], 'AI세탁: ○')
        self.assertNotIn('ocr_text', product)
        self.assertEqual(product['description'], '')
        self.assertEqual(len(original['specs']), 4)

    def test_table_text_uses_no_body_fallback_and_cleans_links(self):
        driver = Mock()
        driver.execute_script.return_value = [('제조회사','삼성전자 (제조사 웹사이트 바로가기)'),
                                              ('AI세탁','○'), ('객체감지','×'), ('빈칸','')]
        specs, raw = crawler._extract_specs(driver)
        self.assertEqual(specs, {'제조회사':'삼성전자', 'AI세탁':'○'})
        self.assertNotIn('객체감지', raw)
        self.assertEqual(driver.execute_script.call_count, 1)
        driver.find_element.assert_not_called()


if __name__ == '__main__':
    unittest.main()
