"""Bounded local endpoint sets and allowlisted offline report comparisons."""
import os
import re
import stat
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .session_probe import PROTOCOLS, SessionInputError, _Failure, _json, _probe, _target

MAX_FILE = 2 * 1024 * 1024
MAX_TARGETS = 16
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,47}\Z')
STAGES = {'initialize', 'initialized', 'ping', 'tools/list'}
FAILURES = {'timeout', 'connection_failed', 'invalid_headers', 'body_limit',
            'truncated_body', 'invalid_json', 'invalid_rpc_response', 'rpc_error',
            'unsupported_content_type', 'event_limit', 'notification_not_accepted',
            'http_rejected', 'invalid_initialize', 'invalid_ping', 'invalid_tools',
            'tool_limit', 'invalid_cursor', 'page_limit', 'missing_rpc_response',
            'invalid_server_request', 'unsupported_server_request', 'ping_limit',
            'invalid_sse_id', 'unresumable_stream', 'resume_limit'}
CLEANUP = {'not_needed', 'not_attempted_deadline', 'terminated', 'unsupported', 'failed'}


def _invalid():
    raise SessionInputError('Invalid bounded endpoint set or supported probe report. See --help and docs/USAGE.md.')


def load_json(path):
    """Read a bounded regular UTF-8 JSON file without blocking on a FIFO."""
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            _invalid()
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            data = stream.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            _invalid()
        return _json(data)
    except (_Failure, OSError, ValueError):
        _invalid()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def validate_targets(inputs, *, timeout=10, max_seconds=30):
    if (type(timeout) is not int or not 1 <= timeout <= 30 or
            type(max_seconds) is not int or not 1 <= max_seconds <= 30 or
            type(inputs) is not dict or set(inputs) != {'schema_version', 'targets'} or
            type(inputs['schema_version']) is not int or inputs['schema_version'] != 1 or
            type(inputs['targets']) is not list or not 1 <= len(inputs['targets']) <= MAX_TARGETS):
        _invalid()
    targets, labels = [], set()
    for row in inputs['targets']:
        if (type(row) is not dict or set(row) != {'label', 'url'} or
                type(row['label']) is not str or not LABEL.fullmatch(row['label']) or
                row['label'] in labels):
            _invalid()
        labels.add(row['label'])
        targets.append((row['label'], _target(row['url'])))
    return targets


def probe_many(inputs, *, timeout=10, max_seconds=30):
    """Prevalidate every explicit target, then check at most four concurrently."""
    targets = validate_targets(inputs, timeout=timeout, max_seconds=max_seconds)
    deadline = time.monotonic() + max_seconds

    def check(item):
        label, target = item
        now = time.monotonic()
        if now >= deadline:
            return {'label': label, 'outcome': 'not_started_deadline', 'report': None}
        report = _probe(target, min(deadline, now + timeout))
        return {'label': label, 'outcome': 'passed' if report['verified'] else 'failed',
                'report': report}

    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as executor:
        rows = list(executor.map(check, targets))
    return {'schema_version': 1, 'report_type': 'mcp-endpoint-set',
            'requestID': str(uuid.uuid4()), 'verified': all(r['outcome'] == 'passed' for r in rows),
            'complete': all(r['report'] is not None for r in rows), 'targets': rows,
            'scope': 'Explicit local connection observations. No endpoint discovery, tool execution or causal diagnosis.'}


def _integer(value, upper):
    if type(value) is not int or not 0 <= value <= upper:
        _invalid()
    return value


def _status(value):
    if value is not None and (type(value) is not int or not 100 <= value <= 599):
        _invalid()
    return value


def _probe_observations(report):
    version = report.get('schema_version')
    if (type(version) is not int or version not in {1, 2, 3} or
            version >= 2 and report.get('report_type') != 'mcp-session-probe' or
            version == 1 and 'report_type' in report or
            type(report.get('verified')) is not bool or
            type(report.get('session_received')) is not bool or
            report.get('protocol_version') is not None and report['protocol_version'] not in PROTOCOLS or
            type(report.get('stages')) is not list or not 1 <= len(report['stages']) <= 7):
        _invalid()
    result = {key: report.get(key) for key in ['verified', 'protocol_version', 'session_received']}
    result['tools_checked'] = _integer(report.get('tools_checked'), 256)
    result['tool_pages_checked'] = _integer(report.get('tool_pages_checked'), 4)
    for key, bound in [('server_pings_answered', 8), ('reconnect_attempts', 2)]:
        result[key] = _integer(report.get(key, 0) if version == 1 else report.get(key), bound)
    stages = []
    expected = ['initialize', 'initialized', 'ping']
    for index, row in enumerate(report['stages']):
        stage = expected[index] if index < 3 else 'tools/list'
        if (type(row) is not dict or row.get('stage') != stage or
                row.get('outcome') not in {'accepted', 'failed'} or
                row['outcome'] == 'failed' and index != len(report['stages']) - 1):
            _invalid()
        stages.append({'stage': stage, 'outcome': row['outcome'], 'http_status': _status(row.get('http_status'))})
    result['stages'] = stages
    cleanup = report.get('cleanup')
    if type(cleanup) is not dict or cleanup.get('outcome') not in CLEANUP:
        _invalid()
    result['cleanup'] = {'outcome': cleanup['outcome'], 'http_status': _status(cleanup.get('http_status'))}
    if 'code' in cleanup:
        if cleanup['code'] not in FAILURES:
            _invalid()
        result['cleanup']['code'] = cleanup['code']
    failure = report.get('failure')
    if report['verified']:
        if (len(stages) < 3 or any(s['outcome'] != 'accepted' for s in stages) or
                report['protocol_version'] not in PROTOCOLS or failure is not None):
            _invalid()
    else:
        if (type(failure) is not dict or failure.get('stage') != stages[-1]['stage'] or
                type(failure.get('code')) is not str or failure['code'] not in FAILURES or
                stages[-1]['outcome'] != 'failed'):
            _invalid()
        result['failure'] = {'stage': failure['stage'], 'code': failure['code']}
    digest = report.get('catalogue_sha256') if version == 3 else None
    if version == 3:
        listed = sum(row['stage'] == 'tools/list' for row in stages)
        complete = report['verified'] and listed > 0
        if ('catalogue_sha256' not in report or
                complete != (digest is not None) or
                digest is not None and (type(digest) is not str or
                                       re.fullmatch('[0-9a-f]{64}', digest) is None) or
                report['tool_pages_checked'] > listed or
                report['verified'] and report['tool_pages_checked'] != listed or
                not listed and report['tools_checked'] != 0):
            _invalid()
    result['catalogue_sha256'] = digest
    return result


def _observations(report):
    if type(report) is not dict:
        _invalid()
    if report.get('report_type') != 'mcp-endpoint-set':
        return {'kind': 'session', **_probe_observations(report)}
    if (type(report.get('schema_version')) is not int or report['schema_version'] != 1 or
            type(report.get('verified')) is not bool or type(report.get('complete')) is not bool or
            type(report.get('targets')) is not list or not 1 <= len(report['targets']) <= MAX_TARGETS):
        _invalid()
    rows = {}
    for row in report['targets']:
        if (type(row) is not dict or type(row.get('label')) is not str or
                not LABEL.fullmatch(row['label']) or row['label'] in rows or
                row.get('outcome') not in {'passed', 'failed', 'not_started_deadline'}):
            _invalid()
        nested = row.get('report')
        if row['outcome'] == 'not_started_deadline':
            if nested is not None:
                _invalid()
            observations = None
        else:
            if type(nested) is not dict:
                _invalid()
            observations = _probe_observations(nested)
            if observations['verified'] != (row['outcome'] == 'passed'):
                _invalid()
        rows[row['label']] = {'outcome': row['outcome'], 'report': observations}
    if (report['verified'] != all(r['outcome'] == 'passed' for r in rows.values()) or
            report['complete'] != all(r['report'] is not None for r in rows.values())):
        _invalid()
    return {'kind': 'endpoint-set', 'verified': report['verified'],
            'complete': report['complete'], 'targets': dict(sorted(rows.items()))}


def compare_reports(left, right):
    """Compare typed observations only. Supplied IDs, text and timings are ignored."""
    try:
        before, after = _observations(left), _observations(right)
    except (TypeError, KeyError, RecursionError):
        _invalid()
    changes = []

    def walk(a, b, path):
        if type(a) is dict and type(b) is dict:
            for key in sorted(a.keys() | b.keys()):
                if key == 'catalogue_sha256' and (a.get(key) is None or b.get(key) is None):
                    continue
                if key not in a or key not in b:
                    change = {'field': path + [key], 'before_present': key in a, 'after_present': key in b}
                    if key in a:
                        change['before'] = a[key]
                    if key in b:
                        change['after'] = b[key]
                    changes.append(change)
                else:
                    walk(a[key], b[key], path + [key])
        elif a != b:
            changes.append({'field': path, 'before': a, 'after': b})

    walk(before, after, [])
    catalogues = []

    def catalogue(a, b, path):
        left_digest = a.get('catalogue_sha256') if a else None
        right_digest = b.get('catalogue_sha256') if b else None
        status = ('unavailable' if left_digest is None or right_digest is None else
                  'unchanged' if left_digest == right_digest else 'changed')
        catalogues.append({'field': path, 'status': status})

    if before['kind'] == after['kind'] == 'endpoint-set':
        for label in sorted(before['targets'].keys() | after['targets'].keys()):
            catalogue(before['targets'].get(label, {}).get('report'),
                      after['targets'].get(label, {}).get('report'), ['targets', label, 'report'])
    else:
        catalogue(before, after, [])
    return {'schema_version': 1, 'report_type': 'mcp-probe-comparison',
            'requestID': str(uuid.uuid4()), 'same_observations': not changes,
            'changes': changes, 'catalogue_comparisons': catalogues,
            'scope': 'Offline comparison of supplied observations. Catalogue status is unavailable without two complete fingerprints. No authenticity or causal claim.'}
