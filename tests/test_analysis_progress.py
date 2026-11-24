import ast
from datetime import datetime
from pathlib import Path
import unittest


class AnalysisProgressTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'server.py'
        nodes = [node for node in ast.parse(source.read_text(encoding='utf-8')).body
                 if isinstance(node, ast.FunctionDef) and node.name == '_make_progress_event']
        self.tasks = {}
        self.scope = {'_tasks': self.tasks, 'datetime': datetime,
                      '_STAGE_NAMES': ['crawl', 'ocr', 'llm_refine', 'public_verify', 'patent_search', 'score'],
                      '_STAGE_LABELS': dict.fromkeys(['crawl', 'ocr', 'llm_refine', 'public_verify', 'patent_search', 'score'], 'stage')}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), self.scope)

    def test_queued_job_does_not_claim_ocr_is_running(self):
        self.tasks['job'] = {'started': False, 'events': [], 'done': False}
        result = self.scope['_make_progress_event']('job', 0)
        self.assertEqual(result['status'], 'queued')
        self.assertIsNone(result['current_stage'])
        self.assertTrue(all(stage['state'] == 'wait' for stage in result['stages']))

    def test_ocr_completion_changes_progress_and_visible_description(self):
        self.tasks['job'] = {'started': True, 'events': [], 'done': False}
        first = self.scope['_make_progress_event']('job', 1)
        updated = self.scope['_make_progress_event']('job', 1, message='3/6개 구간 완료',
                                                   progress={'completed': 3, 'total': 6})
        self.assertGreater(updated['overall_percent'], first['overall_percent'])
        self.assertEqual(updated['stages'][1]['sub_label'], '3/6개 구간 완료')

    def test_failed_task_is_not_reported_completed(self):
        self.tasks['job'] = {'started': True, 'events': [{'type': 'error'}], 'done': True}
        result = self.scope['_make_progress_event']('job', 1, done=True, message='OCR error')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['stages'][1]['state'], 'error')
        self.assertEqual(result['stages'][1]['error_message'], 'OCR error')
        self.assertLess(result['overall_percent'], 100)


if __name__ == '__main__':
    unittest.main()
