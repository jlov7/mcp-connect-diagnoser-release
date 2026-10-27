"""Bounded Streamable HTTP connection checks for an explicit local endpoint.

No credentials, environment proxies, redirects, tool calls or raw response text
enter the report. HTTP observations are not attributed to a particular guard.
"""
from __future__ import annotations

import codecs
import hashlib
import http.client
import json
import math
import socket
import threading
import time
import uuid
from urllib.parse import urlsplit

from . import __version__

PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26')
MAX_BODY = 256 * 1024
MAX_EVENTS = 64
MAX_PAGES = 4
MAX_TOOLS = 256
MAX_SERVER_PINGS = 8
MAX_RECONNECTS = 2


class SessionInputError(ValueError):
    """Invalid local input. Messages never contain supplied values or paths."""


class _Failure(Exception):
    def __init__(self, code, next_step):
        self.code = code
        self.next_step = next_step


class _ResumeNeeded(Exception):
    """A closed SSE response may continue by GET, never by repeating its POST."""


def _target(url):
    message = ('Use an explicit http://127.0.0.1:PORT/path or http://[::1]:PORT/path. '
               'User information, queries, fragments, redirects and HTTPS are unsupported.')
    if (type(url) is not str or not 1 <= len(url) <= 2048 or
            any(ord(c) <= 32 or ord(c) >= 127 for c in url) or '\\' in url):
        raise SessionInputError(message)
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', '::1'} or
                parsed.port is None or not 1 <= parsed.port <= 65535 or
                parsed.username is not None or parsed.password is not None or
                parsed.query or parsed.fragment or '?' in url or '#' in url or
                not parsed.path.startswith('/')):
            raise ValueError
    except ValueError:
        raise SessionInputError(message) from None
    return parsed.hostname, parsed.port, parsed.path


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('non-finite JSON number')


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('non-finite JSON number')
    return number


def _json(data):
    try:
        if type(data) is bytes:
            data = data.decode('utf-8')
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise _Failure('invalid_json', 'Inspect the server response locally; it must be strict UTF-8 JSON.') from None


def _rpc_advice(code):
    # Only protocol-defined labels enter reports, never server messages or data.
    actions = {
        -32700: 'Parse error: inspect JSON serialization and proxy body transformations.',
        -32600: 'Invalid request: check the JSON-RPC envelope and negotiated transport.',
        -32601: 'Method not found: check that the endpoint implements the failed stage for the negotiated version.',
        -32602: 'Invalid params: compare the failed stage parameters with the negotiated protocol schema.',
        -32603: 'Internal error: inspect trusted server-side logs for the failed stage before retrying.',
    }
    if code in actions:
        return ('The server reported ' + actions[code] +
                ' This is a reported error category, not a verified root cause. Response text is omitted.')
    return 'The server returned a JSON-RPC error. Inspect its trusted logs; response text is omitted from this report.'


def _response(message, request_id):
    if (type(message) is not dict or message.get('jsonrpc') != '2.0' or
            type(message.get('id')) is not int or message['id'] != request_id or
            ('result' in message) == ('error' in message)):
        raise _Failure('invalid_rpc_response', 'Check JSON-RPC version, matching integer request ID, and exactly one result or error.')
    if 'error' in message:
        error = message['error']
        if (type(error) is not dict or type(error.get('code')) is not int or
                type(error.get('message')) is not str):
            raise _Failure('invalid_rpc_response', 'Check the JSON-RPC error envelope in trusted server-side logs.')
        raise _Failure('rpc_error', _rpc_advice(error['code']))
    return message['result']


def _header(response, name, *, max_length=1024):
    values = [value for key, value in response.getheaders() if key.lower() == name.lower()]
    if len(values) > 1 or any(len(value) > max_length for value in values):
        raise _Failure('invalid_headers', 'Check duplicated or oversized protocol response headers.')
    return values[0] if values else None


def _chunks(response, stage):
    length = _header(response, 'content-length', max_length=12)
    if length is not None and (not length.isascii() or not length.isdigit() or int(length) > MAX_BODY):
        raise _Failure('body_limit', 'The response exceeds the 256 KiB probe bound or has invalid framing. Inspect it locally.')
    received = 0
    stage.setdefault('response_bytes', 0)
    while True:
        chunk = response.read1(min(4096, MAX_BODY + 1 - received))
        if not chunk:
            if length is not None and received != int(length):
                raise _Failure('truncated_body', 'The response ended before its declared Content-Length. Inspect server/proxy framing before retrying.')
            break
        stage['response_bytes'] += len(chunk)
        received += len(chunk)
        if received > MAX_BODY:
            raise _Failure('body_limit', 'The response exceeds the 256 KiB probe bound. Reduce discovery size or inspect it locally.')
        yield chunk


def _read_rpc(response, stage, request_id, state, context, on_ping, *, resumed=False):
    content_type = _header(response, 'content-type')
    media = content_type.split(';', 1)[0].strip().lower() if content_type else ''
    if media == 'application/json' and not resumed:
        return _response(_json(b''.join(_chunks(response, stage))), request_id)
    if media != 'text/event-stream':
        raise _Failure('unsupported_content_type', 'Use the Streamable HTTP MCP endpoint. Expected application/json or text/event-stream, not a web page.')

    state['sse'] = True
    decoder = codecs.getincrementaldecoder('utf-8-sig')('strict')
    buffer, data, event_id, touched = '', [], None, False
    # Normalize all SSE line endings while preserving a CR at a chunk boundary.
    previous_cr = False
    for chunk in _chunks(response, stage):
        try:
            text = decoder.decode(chunk)
        except UnicodeError:
            raise _Failure('invalid_json', 'The SSE response must be UTF-8.') from None
        for char in text:
            if previous_cr:
                previous_cr = False
                if char == '\n':
                    continue
            if char not in '\r\n':
                buffer += char
                continue
            previous_cr = char == '\r'
            line, buffer = buffer, ''
            if line:
                field, _, value = line.partition(':')
                value = value.removeprefix(' ')
                if field == 'data':
                    data.append(value)
                    touched = True
                elif field == 'id' and '\x00' not in value:
                    event_id, touched = value, True
                elif field == 'retry' and value.isascii() and value.isdigit():
                    # Values larger than any allowed deadline need no large integer.
                    state['retry_ms'] = int(value) if len(value) <= 8 else 10**9
                    touched = True
                continue
            if not touched:
                continue
            state['events'] += 1
            if state['events'] > MAX_EVENTS:
                raise _Failure('event_limit', 'No response arrived within 64 SSE messages. Inspect server notifications locally.')
            if event_id is not None:
                if event_id:
                    if len(event_id) > 1024 or event_id in context['event_ids']:
                        raise _Failure('invalid_sse_id', 'SSE event IDs must be bounded and unique within this session. Values are omitted.')
                    context['event_ids'].add(event_id)
                state['last_event_id'] = event_id or None
            event_data = '\n'.join(data)
            data, event_id, touched = [], None, False
            if not event_data:
                continue
            message = _json(event_data)
            if type(message) is dict and 'method' in message and 'id' in message:
                on_ping(message)
                continue
            if (type(message) is dict and 'id' not in message and
                    message.get('jsonrpc') == '2.0' and
                    type(message.get('method')) is str and
                    message['method'].startswith('notifications/') and
                    'result' not in message and 'error' not in message):
                continue
            return _response(message, request_id)
    try:
        decoder.decode(b'', final=True)
    except UnicodeError:
        raise _Failure('invalid_json', 'The SSE response contains truncated UTF-8.') from None
    raise _ResumeNeeded


def _http_advice(status):
    if 300 <= status < 400:
        return 'Use the final local MCP URL explicitly. This probe never follows redirects.'
    return {
        401: 'The endpoint requires authentication. Use your existing authenticated MCP client and inspect trusted authorization logs. This probe accepts no credentials.',
        403: 'Inspect trusted server and proxy logs for Host, Origin and authorization checks. A 403 alone does not identify the rejecting layer.',
        404: 'Check the configured Streamable HTTP endpoint path and session lifetime.',
        405: 'Check the endpoint path and transport. Legacy HTTP+SSE and stdio are outside this probe.',
        406: 'Check server/proxy Accept handling. This probe sends application/json and text/event-stream.',
        415: 'Check Content-Type handling. This probe sends application/json.',
    }.get(status, 'Inspect trusted server and proxy logs for the failed HTTP stage; the response body is deliberately omitted.')


def _exchange(target, method, payload, headers, deadline, stage, *, notification=False,
              cleanup=False, on_session=None, request_id=None, state=None,
              context=None, on_ping=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _Failure('timeout', 'The absolute probe deadline expired. Check endpoint responsiveness and retry explicitly if appropriate.')
    connection = http.client.HTTPConnection(target[0], target[1], timeout=remaining)
    timer = None
    expired = threading.Event()
    try:
        connection.connect()  # Literal IP only; never consult environment proxies or DNS.
        raw_socket = connection.sock

        def expire():
            expired.set()
            try:
                raw_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        body = json.dumps(payload, separators=(',', ':')).encode() if payload is not None else None
        connection.request(method, target[2], body=body, headers=headers)
        response = connection.getresponse()
        with response:
            stage['http_status'] = response.status
            if cleanup:
                return response.status, None
            if notification:
                if response.status != 202:
                    raise _Failure('notification_not_accepted', 'A notification or server-request response must receive HTTP 202 with no body.')
                if b''.join(_chunks(response, stage)):
                    raise _Failure('notification_not_accepted', 'The notification or server-request response must have no body.')
                return None, None
            if response.status != 200:
                raise _Failure('http_rejected', _http_advice(response.status))
            session = _header(response, 'mcp-session-id')
            if session is not None and (not session or any(not 0x21 <= ord(c) <= 0x7e for c in session)):
                raise _Failure('invalid_headers', 'The MCP session header must contain bounded visible ASCII; its value is omitted.')
            if session is not None and 'MCP-Session-Id' in headers and session != headers['MCP-Session-Id']:
                raise _Failure('invalid_headers', 'The server changed the session ID during an established session.')
            if session is not None and on_session is not None:
                on_session(session)
            result = _read_rpc(response, stage, request_id, state, context, on_ping,
                               resumed=method == 'GET')
            if expired.is_set() or time.monotonic() >= deadline:
                raise TimeoutError
            return result, session
    except _Failure:
        if expired.is_set():
            raise _Failure('timeout', 'The absolute probe deadline expired, including while reading a slow response.') from None
        raise
    except (OSError, http.client.HTTPException, ValueError):
        if state is not None and state['sse'] and not expired.is_set() and time.monotonic() < deadline:
            raise _ResumeNeeded from None
        code = 'timeout' if expired.is_set() or time.monotonic() >= deadline else 'connection_failed'
        advice = ('The absolute probe deadline expired, including while reading a slow response.' if code == 'timeout'
                  else 'Check that the local server is running and the endpoint uses plain HTTP. No credentials or proxy settings were used.')
        raise _Failure(code, advice) from None
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()


def _request(target, method, payload, headers, deadline, stage, *, notification=False,
             cleanup=False, on_session=None, context=None, on_ping=None):
    state = {'last_event_id': None, 'retry_ms': 1000, 'events': 0, 'sse': False}
    request_id = payload.get('id') if payload is not None else None
    while True:
        try:
            return _exchange(target, method, payload, headers, deadline, stage,
                             notification=notification, cleanup=cleanup,
                             on_session=on_session, request_id=request_id, state=state,
                             context=context, on_ping=on_ping)
        except _ResumeNeeded:
            if time.monotonic() >= deadline:
                raise _Failure('timeout', 'The absolute probe deadline expired while awaiting an SSE response.') from None
            cursor = state['last_event_id']
            if cursor is None:
                raise _Failure('unresumable_stream', 'The SSE stream ended without a matching response or a usable event ID. Retry explicitly after inspecting the server.') from None
            # SSE IDs are UTF-8, unlike the separately specified ASCII session ID.
            # Bytes prevent http.client's default Latin-1 encoding from changing
            # or rejecting a Unicode cursor. Keep header controls/edge OWS out.
            if (len(cursor.encode('utf-8')) > 1024 or cursor != cursor.strip(' ') or
                    any(ord(c) < 32 or ord(c) == 127 for c in cursor)):
                raise _Failure('invalid_sse_id', 'Resumption requires an event ID of at most 1024 UTF-8 bytes, without header controls or edge whitespace. Its value is omitted.') from None
            cursor_bytes = cursor.encode('utf-8')
            if context['reconnect_attempts'] >= MAX_RECONNECTS:
                raise _Failure('resume_limit', 'The two-reconnection session bound was reached without a matching response.') from None
            delay = state['retry_ms'] / 1000
            if time.monotonic() + delay >= deadline:
                raise _Failure('timeout', 'The SSE retry delay exceeds the remaining absolute deadline.') from None
            time.sleep(delay)
            context['reconnect_attempts'] += 1
            headers = {'MCP-Protocol-Version': PROTOCOLS[0], **headers,
                       'Accept': 'text/event-stream', 'Last-Event-ID': cursor_bytes}
            method, payload = 'GET', None


def _initialize(result):
    if (type(result) is not dict or result.get('protocolVersion') not in PROTOCOLS or
            type(result.get('serverInfo')) is not dict or
            any(type(result['serverInfo'].get(key)) is not str or
                not 1 <= len(result['serverInfo'][key]) <= 512 for key in ('name', 'version')) or
            type(result.get('capabilities')) is not dict):
        raise _Failure('invalid_initialize', 'Check initialize version, capabilities and serverInfo. Supported versions: 2025-11-25, 2025-06-18, 2025-03-26.')
    capabilities = result['capabilities']
    if 'tools' in capabilities and type(capabilities['tools']) is not dict:
        raise _Failure('invalid_initialize', 'The advertised tools capability must be an object.')
    return result['protocolVersion'], 'tools' in capabilities


def probe_session(url, *, timeout=10):
    """Initialize, notify, ping, optionally list tools, then end a local session.

    Input errors raise SessionInputError. Network/protocol failures are returned as
    bounded observations with recovery advice. No tool is called or server text
    executed. A successful result is a connection check, not MCP conformance.
    """
    target = _target(url)
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise SessionInputError('timeout must be an integer from 1 to 30 seconds')
    return _probe(target, time.monotonic() + timeout)


def _probe(target, deadline):
    report = {'schema_version': 3, 'report_type': 'mcp-session-probe',
              'requestID': str(uuid.uuid4()), 'verified': False,
              'scope': 'Local Streamable HTTP session connection check, not conformance or causal diagnosis.',
              'protocol_version': None, 'session_received': False,
              'tools_checked': 0, 'tool_pages_checked': 0, 'server_pings_answered': 0,
              'reconnect_attempts': 0, 'catalogue_sha256': None, 'stages': [],
              'cleanup': {'outcome': 'not_needed'}}
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    session = None
    context = {'event_ids': set(), 'server_request_ids': set(),
               'reconnect_attempts': 0, 'server_pings_answered': 0}

    def capture_session(value):
        nonlocal session
        session = value
        headers['MCP-Session-Id'] = value
        report['session_received'] = True

    def answer_ping(message):
        incoming_id = message.get('id')
        if (message.get('jsonrpc') != '2.0' or 'result' in message or 'error' in message or
                type(incoming_id) not in {str, int} or
                type(incoming_id) is str and not 1 <= len(incoming_id) <= 128 or
                type(incoming_id) is int and not -(2**53) < incoming_id < 2**53 or
                incoming_id in context['server_request_ids']):
            raise _Failure('invalid_server_request', 'The server sent an invalid or repeated request ID. Its value is omitted.')
        if message.get('method') != 'ping':
            raise _Failure('unsupported_server_request', 'Only server-initiated ping is supported. No requested operation was executed.')
        params = message.get('params', {})
        if (type(params) is not dict or params.keys() - {'_meta'} or
                ('_meta' in params and type(params['_meta']) is not dict)):
            raise _Failure('invalid_server_request', 'A server ping supports only common object metadata, not operation parameters.')
        metadata = params.get('_meta', {})
        if 'progressToken' in metadata and type(metadata['progressToken']) not in {str, int, float}:
            raise _Failure('invalid_server_request', 'A progress token must be a string or finite number.')
        if context['server_pings_answered'] >= MAX_SERVER_PINGS:
            raise _Failure('ping_limit', 'The eight-server-ping session bound was reached.')
        context['server_request_ids'].add(incoming_id)
        reply_headers = {'MCP-Protocol-Version': PROTOCOLS[0], **headers}
        _request(target, 'POST', {'jsonrpc': '2.0', 'id': incoming_id, 'result': {}},
                 reply_headers, deadline, {}, notification=True)
        context['server_pings_answered'] += 1

    def rpc(stage_name, payload, *, notification=False):
        stage = {'stage': stage_name, 'http_status': None}
        report['stages'].append(stage)
        result = _request(target, 'POST', payload, headers, deadline, stage,
                          notification=notification, context=context, on_ping=answer_ping,
                          on_session=capture_session if stage_name == 'initialize' else None)
        stage['outcome'] = 'accepted'
        return result

    try:
        result, _ = rpc('initialize', {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                               'params': {'protocolVersion': PROTOCOLS[0], 'capabilities': {},
                                          'clientInfo': {'name': 'mcp-connect-diagnoser', 'version': __version__}}})
        report['session_received'] = session is not None
        if session is not None:
            headers['MCP-Session-Id'] = session
        version, has_tools = _initialize(result)
        report['protocol_version'] = version
        headers['MCP-Protocol-Version'] = version
        rpc('initialized', {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, notification=True)
        result, _ = rpc('ping', {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'})
        # EmptyResult inherits Result: common metadata and extension fields may
        # exist. They are never interpreted, echoed or treated as authorization.
        if type(result) is not dict or ('_meta' in result and type(result['_meta']) is not dict):
            raise _Failure('invalid_ping', 'A ping must return a result object with object metadata when present.')
        if has_tools:
            seen_cursors, seen_names, cursor = set(), set(), None
            catalogue = []
            for page in range(MAX_PAGES):
                payload = {'jsonrpc': '2.0', 'id': page + 3, 'method': 'tools/list'}
                if cursor is not None:
                    payload['params'] = {'cursor': cursor}
                result, _ = rpc('tools/list', payload)
                if type(result) is not dict or type(result.get('tools')) is not list:
                    raise _Failure('invalid_tools', 'tools/list must return a tools array.')
                for tool in result['tools']:
                    if (type(tool) is not dict or type(tool.get('name')) is not str or
                            not 1 <= len(tool['name']) <= 128 or tool['name'] in seen_names or
                            type(tool.get('inputSchema')) is not dict or tool['inputSchema'].get('type') != 'object'):
                        raise _Failure('invalid_tools', 'Check unique bounded tool names and object input schemas across all discovery pages.')
                    seen_names.add(tool['name'])
                    if len(seen_names) > MAX_TOOLS:
                        raise _Failure('tool_limit', 'Discovery exceeds the 256-tool probe bound. Use your normal MCP client for larger catalogs.')
                    catalogue.append(tool)
                report['tools_checked'] = len(seen_names)
                report['tool_pages_checked'] += 1
                cursor = result.get('nextCursor')
                if cursor is None:
                    canonical = json.dumps(sorted(catalogue, key=lambda tool: tool['name']),
                                           sort_keys=True, separators=(',', ':'),
                                           ensure_ascii=False, allow_nan=False).encode('utf-8')
                    report['catalogue_sha256'] = hashlib.sha256(canonical).hexdigest()
                    break
                if (type(cursor) is not str or not 1 <= len(cursor) <= 2048 or cursor in seen_cursors):
                    raise _Failure('invalid_cursor', 'The server returned an invalid or repeated discovery cursor.')
                seen_cursors.add(cursor)
            else:
                raise _Failure('page_limit', 'Discovery exceeds the four-page probe bound. Use your normal MCP client for more pages.')
        report['verified'] = True
    except _Failure as error:
        if report['stages']:
            report['stages'][-1]['outcome'] = 'failed'
        report['failure'] = {'stage': report['stages'][-1]['stage'], 'code': error.code,
                             'cause': 'unknown', 'next_step': error.next_step}
    finally:
        report['server_pings_answered'] = context['server_pings_answered']
        report['reconnect_attempts'] = context['reconnect_attempts']
        if session is not None:
            headers['MCP-Session-Id'] = session
            if deadline <= time.monotonic():
                report['cleanup'] = {'outcome': 'not_attempted_deadline',
                                     'next_step': 'The server session may remain until its own timeout.'}
            else:
                stage = {'stage': 'terminate', 'http_status': None}
                try:
                    status, _ = _request(target, 'DELETE', None, headers, deadline, stage, cleanup=True)
                    outcome = 'terminated' if status in {200, 202, 204, 404} else 'unsupported' if status == 405 else 'failed'
                    report['cleanup'] = {'outcome': outcome, 'http_status': status}
                except _Failure as error:
                    report['cleanup'] = {'outcome': 'failed', 'code': error.code,
                                         'next_step': 'The server session may remain until its own timeout.'}
    report['summary'] = (f"Initialization, readiness and ping passed; {report['tools_checked']} tool entries checked."
                         if report['verified'] else
                         f"Connection check failed at {report['failure']['stage']} ({report['failure']['code']}).")
    return report
