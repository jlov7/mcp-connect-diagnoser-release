"""Catalogue drift observations, independent of tool invocation or schema evaluation."""
import hashlib
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from mcp_connect_diagnoser.reports import compare_reports
from mcp_connect_diagnoser.session_probe import SessionInputError, _Failure, probe_session


def tool(name='PRIVATE-TOOL'):
    return {'name': name, 'inputSchema': {'type': 'object', 'properties': {
        'PRIVATE-FIELD': {'type': 'string'}}}, 'outputSchema': {'type': 'object'},
        '_meta': {'PRIVATE-META': ['first', 'second']}}


def probe(pages, *, has_tools=True):
    pages = iter(pages)

    def request(target, method, payload, headers, deadline, stage, **kwargs):
        stage['http_status'] = 200
        operation = payload['method']
        if operation == 'initialize':
            return {'protocolVersion': '2025-11-25',
                    'serverInfo': {'name': 'PRIVATE-SERVER', 'version': '1'},
                    'instructions': 'PRIVATE-INSTRUCTIONS',
                    'capabilities': {'tools': {}} if has_tools else {}}, None
        if operation == 'tools/list':
            value = next(pages)
            if isinstance(value, Exception):
                raise value
            return value, None
        return {}, None

    with patch('mcp_connect_diagnoser.session_probe._request', side_effect=request):
        return probe_session('http://127.0.0.1:9/mcp')


class CatalogueTests(unittest.TestCase):
    def test_complete_catalogue_is_canonical_across_keys_tools_and_pages(self):
        first, second = tool(), tool('PRIVATE-SECOND')
        before = probe([{'tools': [first, second]}])
        reordered = json.loads(json.dumps(first, sort_keys=True))
        after = probe([{'tools': [second], 'nextCursor': 'PRIVATE-CURSOR'},
                       {'tools': [reordered]}])
        expected = hashlib.sha256(json.dumps([second, first], sort_keys=True,
                    separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.assertEqual(before['schema_version'], 3)
        self.assertEqual(before['catalogue_sha256'], expected)
        self.assertEqual(after['catalogue_sha256'], expected)
        self.assertEqual(compare_reports(before, after)['catalogue_comparisons'],
                         [{'field': [], 'status': 'unchanged'}])
        self.assertNotIn('PRIVATE', json.dumps(before))

    def test_same_count_name_input_output_and_metadata_changes_are_observed(self):
        original = tool()
        before = probe([{'tools': [original]}])
        changed = []
        for field, value in [('name', 'PRIVATE-RENAMED'),
                             ('inputSchema', {'type': 'object', 'properties': {'PRIVATE-FIELD': {'type': 'integer'}}}),
                             ('outputSchema', {'type': 'object', 'properties': {'answer': {'type': 'string'}}}),
                             ('_meta', {'PRIVATE-META': ['second', 'first']})]:
            candidate = deepcopy(original)
            candidate[field] = value
            changed.append(candidate)
        for candidate in changed:
            after = probe([{'tools': [candidate]}])
            comparison = compare_reports(before, after)
            self.assertFalse(comparison['same_observations'])
            self.assertEqual(comparison['catalogue_comparisons'][0]['status'], 'changed')
            self.assertNotIn('PRIVATE', json.dumps(comparison))

    def test_missing_capability_partial_and_duplicate_catalogues_are_unavailable(self):
        for report in [probe([], has_tools=False),
                       probe([{'tools': [tool()], 'nextCursor': 'next'},
                              _Failure('rpc_error', 'constant advice')]),
                       probe([{'tools': [tool(), tool()]}]),
                       probe([{'tools': [tool()], 'nextCursor': 'next'},
                              {'tools': [tool()]}]),
                       probe([{'tools': [tool()], 'nextCursor': ''}])]:
            self.assertIsNone(report['catalogue_sha256'])
            self.assertEqual(compare_reports(report, report)['catalogue_comparisons'][0]['status'],
                             'unavailable')
        self.assertIsNotNone(probe([{'tools': []}])['catalogue_sha256'])

    def test_old_reports_stay_supported_with_unknown_catalogue(self):
        current = probe([{'tools': [tool()]}])
        for version in (1, 2):
            old = deepcopy(current)
            old['schema_version'] = version
            old.pop('catalogue_sha256')
            if version == 1:
                for field in ['report_type', 'reconnect_attempts', 'server_pings_answered']:
                    old.pop(field)
            self.assertTrue(compare_reports(old, old)['same_observations'])
            self.assertEqual(compare_reports(old, current)['catalogue_comparisons'][0]['status'],
                             'unavailable')

    def test_digest_shape_and_availability_are_validated_without_echo(self):
        valid = probe([{'tools': [tool()]}])
        for value in [True, 42, [], {}, 'PRIVATE', 'a' * 63, 'A' * 64, 'g' * 64]:
            invalid = dict(valid, catalogue_sha256=value)
            with self.subTest(value=value), self.assertRaises(SessionInputError) as error:
                compare_reports(valid, invalid)
            self.assertNotIn('PRIVATE', str(error.exception))
        for report in [probe([], has_tools=False), probe([_Failure('rpc_error', 'constant')])]:
            report['catalogue_sha256'] = 'a' * 64
            with self.assertRaises(SessionInputError):
                compare_reports(valid, report)
        invalid = deepcopy(valid)
        invalid.pop('catalogue_sha256')
        with self.assertRaises(SessionInputError):
            compare_reports(valid, invalid)
        for field, value in [('catalogue_sha256', None), ('tool_pages_checked', 0)]:
            invalid = dict(valid, **{field: value})
            with self.assertRaises(SessionInputError):
                compare_reports(valid, invalid)

    def test_endpoint_catalogue_status_preserves_partial_availability(self):
        known = probe([{'tools': [tool()]}])
        unknown = probe([], has_tools=False)
        report = {'schema_version': 1, 'report_type': 'mcp-endpoint-set',
                  'verified': True, 'complete': True, 'targets': [
                      {'label': label, 'outcome': 'passed', 'report': value}
                      for label, value in [('known', known), ('unknown', unknown)]]}
        comparison = compare_reports(report, report)
        self.assertEqual([row['status'] for row in comparison['catalogue_comparisons']],
                         ['unchanged', 'unavailable'])


if __name__ == '__main__':
    unittest.main()
