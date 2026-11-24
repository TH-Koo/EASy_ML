"""Bound expensive analysis work and reuse an owner's active product job."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
import threading
from urllib.parse import parse_qs, urlsplit, urlunsplit
import uuid


class AnalysisQueueFull(Exception):
    pass


def product_key(url):
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or '').lower()
    code = (parse_qs(parsed.query).get('pcode') or [''])[0]
    if (host == 'danawa.com' or host.endswith('.danawa.com')) and code.isdigit():
        return f'danawa:{code}'
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ''))


class AnalysisScheduler:
    def __init__(self, tasks, max_workers=1, max_pending=8):
        self.tasks = tasks
        self.max_pending = max(1, max_pending)
        self.executor = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix='analysis')
        self.lock = threading.Lock()

    def submit(self, url, user_id, runner):
        key = product_key(url)
        with self.lock:
            pending = [(ident, task) for ident, task in self.tasks.items() if not task.get('done')]
            for ident, task in pending:
                if task.get('product_key') == key and task.get('user_id') == user_id:
                    return ident, True
            if len(pending) >= self.max_pending:
                raise AnalysisQueueFull()
            ident = str(uuid.uuid4())
            task = {'events': [], 'done': False, 'started': False, 'start_time': datetime.now(),
                    'product_key': key, 'user_id': user_id}
            self.tasks[ident] = task
            try:
                self.executor.submit(self._run, ident, task, url, user_id, runner)
            except Exception:
                del self.tasks[ident]
                raise
            return ident, False

    @staticmethod
    def _run(ident, task, url, user_id, runner):
        task['started'] = True
        task['start_time'] = datetime.now()
        try:
            runner(ident, url, user_id)
        except Exception:
            logging.exception('Analysis worker failed: %s', ident)
            task['events'].append({'type': 'error', 'message': '분석 도중 오류가 발생했어요. 다시 시도해 주세요.'})
            task['done'] = True

    def shutdown(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
