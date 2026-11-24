"""Reuse successful public evidence queries without changing provider responses."""
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import tempfile
import threading
import time


_LOCKS = tuple(threading.Lock() for _ in range(64))


def _cacheable(result):
    if not isinstance(result, dict):
        return False
    if any(result.get(key) for key in ('error', 'errors', 'warnings', 'collection_partial')):
        return False
    if result.get('status') in {'error', '조회 불가', '스킵', 'skipped'}:
        return False
    # Some legacy providers hide request failures behind an empty result.
    # Cache confirmed data only, so those failures are always retried.
    if any(isinstance(result.get(key), list) and result[key] for key in ('records', 'items')):
        return True
    return bool(result.get('evidence')) and bool(result.get('score') or result.get('total_score'))


def _query_key(name, function, args, revision):
    source = inspect.getsourcefile(function)
    fingerprint = hashlib.sha256(Path(source).read_bytes()).hexdigest() if source else function.__qualname__
    if name == 'KIPRIS':
        fingerprint += hashlib.sha256(Path(__file__).with_name('patent_scraper.py').read_bytes()).hexdigest()
    payload = json.dumps([1, name, function.__module__, function.__qualname__, fingerprint, revision, args],
                         ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def query_cached(name, function, *args, revision=''):
    ttl = max(0, float(os.getenv('EASY_EVIDENCE_CACHE_SECONDS', '300')))
    if not ttl:
        return function(*args)
    try:
        key = _query_key(name, function, args, revision)
    except (OSError, TypeError, ValueError):
        return function(*args)
    directory = Path(os.getenv('EASY_EVIDENCE_CACHE_DIR') or Path(tempfile.gettempdir()) / 'easy_evidence_cache')
    path = directory / (key + '.json')
    with _LOCKS[int(key[:8], 16) % len(_LOCKS)]:
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
            if 0 <= time.time() - cached['saved_at'] < ttl and _cacheable(cached['result']):
                return copy.deepcopy(cached['result'])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        result = function(*args)
        if _cacheable(result):
            temporary = None
            try:
                directory.mkdir(parents=True, exist_ok=True)
                payload = json.dumps({'saved_at': time.time(), 'result': result}, ensure_ascii=False)
                with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=directory, delete=False) as output:
                    temporary = output.name
                    output.write(payload)
                os.replace(temporary, path)
                temporary = None
            except (OSError, TypeError, ValueError):
                pass
            finally:
                if temporary:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass
        return result
