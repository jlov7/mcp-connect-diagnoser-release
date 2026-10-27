"""Verify native SDK metadata sessions and its typed-construction boundary."""
import argparse
import json
import os
import select
import socket
import subprocess
from pathlib import Path

from mcp_connect_diagnoser.session_probe import probe_session

MODES = ('response-json', 'response-sse', 'request-string', 'request-integer')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, help='locked native SDK interpreter')
    parser.add_argument('--output', required=True, type=Path, help='new private evidence file')
    args = parser.parse_args()
    runtime = json.loads(subprocess.check_output([args.python, '-B', '-c',
        'import importlib.metadata as m,platform,json; print(json.dumps({"python":platform.python_version(),"mcp":m.version("mcp")}))'], timeout=10))
    if runtime != {'python': '3.13.15', 'mcp': '2.3.0'}:
        raise ValueError('the native gate requires its declared locked SDK runtime')
    report = {'schema': 'mcp-native-ping-metadata-v1', 'runtime': runtime,
              'verified': False, 'cases': [], 'constructor_boundary': None,
              'scope': 'Four owned native SDK sessions and one unsupported typed-construction case.'}
    with open(args.output, 'x', encoding='utf-8',
              opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        try:
            run_cases(args.python, report)
            fixture = Path(__file__).resolve().parents[1] / 'tests/sdk/ping_metadata_server.py'
            boundary = json.loads(subprocess.check_output(
                [args.python, '-B', str(fixture), 'fraction-construction'], timeout=10))
            report['constructor_boundary'] = boundary
            if boundary != {'outcome': 'unsupported_by_pinned_sdk',
                            'wire_request_emitted': False,
                            'error_types': ['string_type', 'int_from_float']}:
                raise RuntimeError('the locked SDK constructor boundary changed')
            report['verified'] = True
        finally:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'verified': report['verified'], 'native_metadata_sessions': len(report['cases']),
                      'constructor_boundary': report['constructor_boundary']['outcome']}))


def run_cases(python, report):
    fixture = Path(__file__).resolve().parents[1] / 'tests/sdk/ping_metadata_server.py'
    for mode in MODES:
        child = subprocess.Popen([python, '-B', str(fixture), mode],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        port = None
        try:
            ready, _, _ = select.select([child.stdout], [], [], 10)
            if not ready:
                raise RuntimeError('native metadata fixture startup exceeded deadline')
            value = child.stdout.readline().strip()
            if not value.isdigit() or not 1 <= int(value) <= 65535:
                raise RuntimeError('native metadata fixture did not publish a bounded port')
            port = int(value)
            result = probe_session('http://127.0.0.1:' + value + '/mcp', timeout=5)
            case = {'mode': mode, 'report': result, 'listener_closed': False}
            report['cases'].append(case)
            expected_pings = 1 if mode.startswith('request-') else 0
            if (not result['verified'] or result['server_pings_answered'] != expected_pings or
                    result['tools_checked'] != 1 or result['cleanup']['outcome'] != 'terminated' or
                    'NATIVE-METADATA-DO-NOT-ECHO' in json.dumps(result)):
                raise RuntimeError('native metadata check failed; inspect the private report')
        finally:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
            if port is not None:
                with socket.socket() as connection:
                    connection.settimeout(0.2)
                    closed = connection.connect_ex(('127.0.0.1', port)) != 0
                if report['cases'] and report['cases'][-1]['mode'] == mode:
                    report['cases'][-1]['listener_closed'] = closed
                if not closed:
                    raise RuntimeError('native fixture listener remained open')


if __name__ == '__main__':
    main()
