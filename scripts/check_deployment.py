"""Wait for the frontend AND the expected backend API, not just systemd state."""
from __future__ import annotations

import argparse
import json
import time
from urllib.error import URLError
from urllib.request import urlopen


def probe_services(frontend_url: str, backend_url: str, request_timeout: float = 3) -> list[str]:
    failures = []
    try:
        with urlopen(frontend_url.rstrip('/') + '/', timeout=request_timeout) as response:
            if response.status != 200:
                failures.append(f'frontend HTTP {response.status}')
    except (OSError, URLError) as error:
        failures.append(f'frontend: {error}')
    try:
        with urlopen(backend_url.rstrip('/') + '/openapi.json', timeout=request_timeout) as response:
            schema = json.load(response)
        paths = schema.get('paths', {})
        for route, method in [('/api/analyze', 'post'), ('/api/analyze/{analysis_id}/result', 'get')]:
            if method not in paths.get(route, {}):
                failures.append(f'backend API missing: {method.upper()} {route}')
    except (OSError, URLError, ValueError, AttributeError, TypeError) as error:
        failures.append(f'backend: {error}')
    return failures


def wait_for_services(frontend_url: str, backend_url: str, timeout: float = 60, interval: float = 2) -> None:
    deadline = time.monotonic() + timeout
    consecutive = 0
    last_failures = []
    while True:
        last_failures = probe_services(frontend_url, backend_url)
        consecutive = 0 if last_failures else consecutive + 1
        if consecutive >= 3:
            print('Frontend and backend API ready (3 consecutive checks)', flush=True)
            return
        if time.monotonic() >= deadline:
            reason = '; '.join(last_failures) or 'services did not stay ready for 3 consecutive checks'
            raise RuntimeError(f'Deployment readiness failed: {reason}')
        print('Waiting: ' + ('; '.join(last_failures) or f'ready {consecutive}/3'), flush=True)
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-url', default='http://127.0.0.1:3000')
    parser.add_argument('--backend-url', default='http://127.0.0.1:8000')
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    try:
        wait_for_services(args.frontend_url, args.backend_url, timeout=args.timeout)
    except RuntimeError as error:
        print(str(error), flush=True)
        print('Inspect server logs: sudo journalctl -u easy-backend.service -n 60 --no-pager', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
