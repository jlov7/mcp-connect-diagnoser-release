"""Explicit optional SDK wire gate. Requires tests/sdk dependencies; never silently skips."""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import selectors
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from .core import diagnose
from .proxy import LoopbackProxy

INITIALIZE = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-11-25', 'capabilities': {},
    'clientInfo': {'name': 'synthetic-repro', 'version': '1.0.0'}}}).encode()
SAFE_HEADERS = ('content-type', 'www-authenticate')
# Frozen before first execution. No case is selected or removed based on its outcome.
CASES = [{'name': f'mask-{mask}', 'host_invalid': bool(mask & 1),
              'origin': 'https://bad.invalid' if mask & 2 else 'http://localhost:7000',
              'bearer': 'wrong-synthetic' if mask & 4 else 'synthetic-sdk-token'}
         for mask in range(8)] + [
    {'name': 'absent-origin', 'origin': None}, {'name': 'null-origin', 'origin': 'null'},
    {'name': 'missing-auth', 'bearer': None}, {'name': 'malformed-json', 'body': '{'},
    {'name': 'unsupported-accept', 'accept': 'text/plain'},
    {'name': 'invalid-content-type', 'content_type': 'text/plain'}]


def capture(port, case):
    """No ambient proxies, redirects, external addresses, request logs or unbounded reads."""
    headers = {'Host': 'bad.invalid' if case.get('host_invalid') else f'127.0.0.1:{port}',
               'Content-Type': case.get('content_type', 'application/json'),
               'Accept': case.get('accept', 'application/json, text/event-stream')}
    origin = case.get('origin', 'http://localhost:7000')
    bearer = case.get('bearer', 'synthetic-sdk-token')
    if origin is not None:
        headers['Origin'] = origin
    if bearer is not None:
        headers['Authorization'] = f'Bearer {bearer}'
    body = case['body'].encode() if 'body' in case else INITIALIZE
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        conn.request('POST', '/mcp', body=body, headers=headers)
        response = conn.getresponse()
        data = response.read(8193)
        if len(data) > 8192:
            raise ValueError('SDK response exceeds 8192-byte evidence bound')
        safe = {name: response.headers.get_all(name, []) for name in SAFE_HEADERS}
        return {'status': response.status, 'headers': safe,
                'body_base64': base64.b64encode(data).decode(),
                'body_sha256': hashlib.sha256(data).hexdigest(),
                'diagnostic': diagnose(response.status, {})}
    finally:
        conn.close()


@contextmanager
def sdk_server(command, log_path=None):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(10):
                raise TimeoutError('SDK server did not announce a port in 10 seconds')
            line = process.stdout.readline(32)
        if not line.strip().isdigit() or not 0 < int(line) < 65536:
            raise RuntimeError('SDK server failed before readiness')
        port = int(line)
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise TimeoutError('SDK server did not become ready')
                time.sleep(.05)
        yield port
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=3)
        if log_path is not None:
            Path(log_path).write_bytes((stdout + b'\n' + stderr)[:16384])


def frozen_definitions():
    return {'versions': {'python-mcp': '2.3.0', 'typescript-server': '2.3.1',
                               'typescript-express': '2.0.2', 'typescript-node': '2.0.0'},
                   'cases': CASES, 'compositions': ['factory', 'auth-first', 'security-first'],
                   'routes': ['direct', 'proxy'], 'initialize_base64': base64.b64encode(INITIALIZE).decode()}


def run_matrix(sdk_dir, python, node, output):
    output = Path(output)
    definitions = frozen_definitions()
    record = {'scope': 'Native loopback SDK middleware reproduction, not protocol conformance or deployment evidence.',
              'definitions': definitions, 'definition_sha256': hashlib.sha256(
                  json.dumps(definitions, sort_keys=True).encode()).hexdigest(), 'rows': [], 'complete': False}
    with output.open('x') as stream:
        stream.write(json.dumps(record, indent=2) + '\n')
    try:
        for sdk, executable, script in [('python', python, 'python_server.py'),
                                         ('typescript', node, 'typescript_server.mjs')]:
            for composition in definitions['compositions']:
                log_path = output.with_name(f'{output.stem}-{sdk}-{composition}.log')
                with (sdk_server([str(executable), str(Path(sdk_dir) / script), composition], log_path) as port,
                      LoopbackProxy(f'http://127.0.0.1:{port}/mcp') as proxy):
                    for route, target in [('direct', port), ('proxy', proxy.port)]:
                        for case in CASES:
                            record['rows'].append({'sdk': sdk, 'composition': composition,
                                                   'route': route, 'case': case['name'],
                                                   **capture(target, case)})
        record['complete'] = True
    finally:
        output.write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-dir', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run_matrix(args.sdk_dir, args.python, args.node, args.output)
    print(json.dumps({'complete': result['complete'], 'requests': len(result['rows']),
                      'definition_sha256': result['definition_sha256']}))
