"""Strict offline verification of the frozen native initialize/middleware matrix."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import stat
from collections import Counter

from .core import diagnose
from .sdk_repro import SAFE_HEADERS, frozen_definitions

DEFINITION_SHA256 = 'e9e7811a19276af102b78197ee4ba3a69eec8d5569459690ccf93a487eb49d7f'
SCOPE = 'Native loopback SDK middleware reproduction, not protocol conformance or deployment evidence.'
MAX_RECORD_BYTES = 2 * 1024 * 1024


class RecordError(ValueError):
    """An invalid record; messages contain locations, never supplied wire values."""


def _require(condition, message):
    if not condition:
        raise RecordError(message)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate JSON object key')
        result[key] = value
    return result


def _json(data):
    def invalid_constant(_):
        raise RecordError('non-finite JSON number')
    try:
        return json.loads(data, object_pairs_hook=_object, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RecordError('invalid JSON; supply a complete UTF-8 native record') from exc


def load_record(path):
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode), 'record must be a regular file')
        _require(info.st_size <= MAX_RECORD_BYTES, 'record exceeds the 2 MiB limit')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            data = stream.read(MAX_RECORD_BYTES + 1)
    except OSError as exc:
        raise RecordError('cannot read record; check the input file and permissions') from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    _require(len(data) <= MAX_RECORD_BYTES, 'record exceeds the 2 MiB limit')
    try:
        record = _json(data.decode('utf-8', errors='strict'))
    except UnicodeError as exc:
        raise RecordError('record must be UTF-8') from exc
    return summarize(record)


def summarize(record):
    """Validate completeness/integrity; compare observations without causal inference."""
    _require(type(record) is dict and set(record) == {
        'scope', 'definitions', 'definition_sha256', 'rows', 'complete'},
        'record must contain exactly the frozen record fields')
    _require(record['scope'] == SCOPE and record['complete'] is True,
             'record is incomplete or has an unsupported scope')
    definitions = frozen_definitions()
    expected_json = json.dumps(definitions, sort_keys=True)
    _require(json.dumps(record['definitions'], sort_keys=True) == expected_json and
             record['definition_sha256'] == DEFINITION_SHA256 and
             hashlib.sha256(expected_json.encode()).hexdigest() == DEFINITION_SHA256,
             'definition does not match the frozen 168-request experiment')
    rows = record['rows']
    _require(type(rows) is list and len(rows) == 168, 'expected exactly 168 native response rows')
    expected = {(sdk, composition, route, case['name']) for sdk in ['python', 'typescript']
                for composition in definitions['compositions'] for route in definitions['routes']
                for case in definitions['cases']}
    indexed = {}
    positive_failures = []
    for index, row in enumerate(rows):
        where = f'row {index}'
        _require(type(row) is dict and set(row) == {'sdk', 'composition', 'route', 'case',
                 'status', 'headers', 'body_base64', 'body_sha256', 'diagnostic'},
                 f'{where}: unsupported or missing response fields')
        identity = tuple(row[key] for key in ['sdk', 'composition', 'route', 'case'])
        _require(all(type(value) is str for value in identity), f'{where}: invalid configuration')
        _require(identity in expected and identity not in indexed,
                 f'{where}: duplicate or out-of-matrix configuration')
        _require(type(row['status']) is int and 100 <= row['status'] <= 599,
                 f'{where}: status must be an HTTP integer')
        headers = row['headers']
        _require(type(headers) is dict and set(headers) == set(SAFE_HEADERS),
                 f'{where}: expected only the two safe response headers')
        for values in headers.values():
            _require(type(values) is list and len(values) <= 1 and all(
                type(value) is str and len(value) <= 1024 and all(
                    32 <= ord(char) <= 126 for char in value) for value in values),
                f'{where}: invalid or duplicate safe response header')
        encoded = row['body_base64']
        _require(type(encoded) is str and len(encoded) <= 10924, f'{where}: oversized body encoding')
        try:
            body = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RecordError(f'{where}: invalid base64 body') from exc
        _require(len(body) <= 8192 and base64.b64encode(body).decode() == encoded,
                 f'{where}: noncanonical or oversized body')
        _require(row['body_sha256'] == hashlib.sha256(body).hexdigest(),
                 f'{where}: body hash mismatch')
        _require(row['diagnostic'] == diagnose(row['status'], {}),
                 f'{where}: native diagnosis must remain unknown')
        indexed[identity] = row
        if row['case'] in {'mask-0', 'absent-origin'}:
            try:
                result = _json(body)['result']
                good = (row['status'] == 200 and result['serverInfo']['name'] == 'sdk-repro'
                        and result['protocolVersion'] == '2025-11-25')
            except (RecordError, KeyError, TypeError):
                good = False
            if not good:
                positive_failures.append(dict(zip(['sdk', 'composition', 'route', 'case'], identity)))
    _require(set(indexed) == expected, 'missing native configuration')
    differences = []
    for identity, direct in indexed.items():
        if identity[2] != 'direct':
            continue
        proxy = indexed[(identity[0], identity[1], 'proxy', identity[3])]
        fields = [label for key, label in [('status', 'status'), ('body_base64', 'body'),
                  ('headers', 'headers')] if direct[key] != proxy[key]]
        if fields:
            differences.append({'sdk': identity[0], 'composition': identity[1],
                                'case': identity[3], 'fields': fields})
    configurations = []
    for sdk in ['python', 'typescript']:
        for composition in definitions['compositions']:
            for route in definitions['routes']:
                subset = [row for key, row in indexed.items() if key[:3] == (sdk, composition, route)]
                configurations.append({'sdk': sdk, 'composition': composition, 'route': route,
                                       'requests': len(subset),
                                       'statuses': dict(sorted(Counter(str(r['status']) for r in subset).items())),
                                       'all_invalid_status': indexed[(sdk, composition, route, 'mask-7')]['status']})
    return {'verified': not differences and not positive_failures, 'requests': 168, 'pairs': 84,
            'definition_sha256': DEFINITION_SHA256, 'versions': definitions['versions'],
            'positive_controls': {'checked': 24, 'failures': positive_failures},
            'differences': differences, 'configurations': configurations,
            'unknown_diagnoses': 168, 'diagnostic': diagnose(0, {}),
            'scope': SCOPE, 'provenance': 'Supplied runtime record; integrity is not authenticity or independent replication.'}
