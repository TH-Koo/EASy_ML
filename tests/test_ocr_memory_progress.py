import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class OcrMemoryProgressTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('ocr_performance_test', ROOT / 'logic/ocr_analyzer.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'easyocr': types.SimpleNamespace(Reader=MagicMock())}):
            spec.loader.exec_module(self.module)

    def test_decoder_uses_grayscale_and_emits_actual_completed_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.png'
            cv2.imencode('.png', np.zeros((3500, 300, 3), dtype=np.uint8))[1].tofile(str(image))
            reader = MagicMock()
            reader.readtext.side_effect = [['AI 세탁'], ['에너지 절약']]
            progress = []
            with patch.object(self.module, 'get_ocr_reader', return_value=(reader, 'CPU')), \
                 patch.object(self.module.cv2, 'imdecode', wraps=cv2.imdecode) as decode, \
                 contextlib.redirect_stdout(io.StringIO()):
                result = self.module.analyze_ai_washing(str(image), use_cache=False, progress_callback=progress.append)
            self.assertEqual(decode.call_args.args[1], cv2.IMREAD_GRAYSCALE)
            self.assertTrue(all(call.args[0].ndim == 2 for call in reader.readtext.call_args_list))
            self.assertEqual([item['completed'] for item in progress], [0, 1, 2])
            self.assertTrue(all(item['total'] == 2 for item in progress))
            self.assertEqual(result['extracted_text'], 'AI 세탁 에너지 절약')

    def test_reader_work_is_serialized_even_outside_web_scheduler(self):
        lock = threading.Lock()
        active = maximum = 0
        def work(*args):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return {'extracted_text': 'AI'}
        with patch.object(self.module, '_analyze_ai_washing_locked', side_effect=work):
            threads = [threading.Thread(target=self.module.analyze_ai_washing, args=('image.png',)) for _ in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(2)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(maximum, 1)


if __name__ == '__main__':
    unittest.main()
