import os
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logic"))
import dart_scraper  # noqa: E402


class DartReaderFallbackTest(unittest.TestCase):
    def setUp(self):
        dart_scraper._DART_READER = None
        dart_scraper._DART_READER_DAY = ""
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"EASY_DART_CACHE_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
        dart_scraper._DART_READER = None

    def test_unwritable_docs_cache_falls_back(self):
        # 서버에서 docs_cache 가 다른 계정 소유라 OpenDartReader 생성이 실패하던 상황
        codes = pd.DataFrame({"corp_code": ["00126380"], "corp_name": ["삼성전자"], "stock_code": ["005930"]})
        denied = PermissionError(13, "Permission denied", "docs_cache/opendartreader_corp_codes_20260913.pkl")
        with mock.patch.object(dart_scraper, "OpenDartReader", side_effect=denied), \
                mock.patch.object(dart_scraper._DART_LIST_BACKEND, "corp_codes", return_value=codes) as fetch:
            reader = dart_scraper._open_dart_reader("key")
            again = dart_scraper._open_dart_reader("key")
        self.assertIs(reader, again)  # 하루 한 번만 만든다
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(reader.api_key, "key")
        self.assertEqual(list(reader.corp_codes["corp_name"]), ["삼성전자"])
        self.assertTrue(any(f.endswith(".pkl") for f in os.listdir(self.tmp.name)))


if __name__ == "__main__":
    unittest.main()
