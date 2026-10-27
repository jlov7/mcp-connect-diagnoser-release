"""Check the client against native stateful JSON and SSE SDK sessions."""
import argparse
import json
import os
import select
import subprocess
from pathlib import Path

from mcp_connect_diagnoser.session_probe import probe_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, help='locked native SDK interpreter')
    parser.add_argument('--output', required=True, type=Path, help='new private evidence file')
    args = parser.parse_args()
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    report = {'scope': 'Native Python SDK 2.3.0 local stateful session checks.',
              'verified': False, 'reports': []}
    try:
        fixture = Path(__file__).resolve().parents[1] / 'tests/sdk/session_server.py'
        for mode in ('json', 'sse'):
            child = subprocess.Popen([args.python, str(fixture), mode], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
            try:
                ready, _, _ = select.select([child.stdout], [], [], 10)
                if not ready:
                    raise RuntimeError('native fixture startup exceeded deadline')
                port = child.stdout.readline().strip()
                if not port.isdigit() or not 1 <= int(port) <= 65535:
                    raise RuntimeError('native fixture did not publish a bounded local port')
                result = probe_session('http://127.0.0.1:' + port + '/mcp')
                report['reports'].append({'transport': mode, **result})
                if (not result['verified'] or not result['session_received'] or
                        result['tools_checked'] != 1 or result['cleanup']['outcome'] != 'terminated'):
                    raise RuntimeError('native session check failed; inspect private output')
            finally:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
                child.stdout.close()
        report['verified'] = True
    finally:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'verified': report['verified'], 'native_sessions': len(report['reports'])}))


if __name__ == '__main__':
    main()
