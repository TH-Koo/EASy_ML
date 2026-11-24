import contextlib
from dataclasses import asdict
from datetime import datetime
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from analysis_engine import OntologyAnalysisEngine


class EngineDebugTests(unittest.TestCase):
    def test_debug_switch_does_not_change_scoring(self):
        results, outputs = [], []
        for enabled in ['0','1']:
            output = io.StringIO()
            with patch.dict(os.environ, {'EASY_ENGINE_DEBUG':enabled}), \
                 patch('analysis_engine.datetime') as clock, contextlib.redirect_stdout(output):
                clock.now.return_value = datetime(2026, 11, 24)
                engine = OntologyAnalysisEngine(str(Path(__file__).resolve().parents[1] / 'ontology'))
                result = engine.analyze([
                    {'evidence_id':'seller-1','source_type':'seller_page','status':'verified',
                     'title':'AI세탁','text':'AI세탁 AI에너지절약','relation_type':'direct_model'}
                ], ad_text='AI세탁 AI에너지절약', product_type='세탁기')
            data = asdict(result)
            data.pop('generated_at', None)
            results.append(data)
            outputs.append(output.getvalue())
        self.assertEqual(results[0], results[1])
        self.assertNotIn('EVIDENCE DEBUG', outputs[0])
        self.assertEqual(outputs[1].count('EVIDENCE DEBUG'), 1)


if __name__ == '__main__':
    unittest.main()
