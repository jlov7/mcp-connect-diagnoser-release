"""Check an explicit local MCP session or verify an offline native record."""
import argparse
import json
import os
import sys
import uuid

from . import __version__
from .native_records import RecordError, load_record
from .reports import compare_reports, load_json, probe_many, validate_targets
from .session_probe import SessionInputError, probe_session


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RecordError('Use summarize, probe, probe-many or compare; see --help.')


def main(argv=None):
    parser = Parser(prog='mcp-connect-diagnoser', description=__doc__)
    parser.add_argument('--version', action='version', version='%(prog)s ' + __version__)
    commands = parser.add_subparsers(dest='command', required=True)
    summarize = commands.add_parser('summarize', help='verify a complete frozen native JSON record offline')
    summarize.add_argument('record', help='complete native JSON record, at most 2 MiB')
    probe = commands.add_parser('probe', help='check an explicit literal-loopback Streamable HTTP endpoint')
    probe.add_argument('url', help='http://127.0.0.1:PORT/path or http://[::1]:PORT/path')
    probe.add_argument('--timeout', type=int, default=10, help='absolute deadline, 1..30 seconds (default 10)')
    probe.add_argument('--output', help='new private JSON report file; existing paths are refused before connecting')
    many = commands.add_parser('probe-many', help='check an explicit bounded set of local endpoints')
    many.add_argument('targets', help='schema-version-1 target set JSON, at most 16 safe labels and literal-loopback URLs')
    many.add_argument('--timeout', type=int, default=10, help='per-target deadline, 1..30 seconds')
    many.add_argument('--max-seconds', type=int, default=30, help='total deadline, 1..30 seconds, at most four concurrent targets')
    many.add_argument('--output', help='new private JSON report file')
    compare = commands.add_parser('compare', help='compare two saved probe or endpoint-set reports offline')
    compare.add_argument('left')
    compare.add_argument('right')
    compare.add_argument('--output', help='new private JSON comparison file')
    request_id = str(uuid.uuid4())
    output = None
    try:
        args = parser.parse_args(argv)
        if args.command == 'summarize':
            summary = load_record(args.record)
        elif args.command == 'probe':
            # Validate before reserving output, and reserve before any network activity.
            from .session_probe import _target
            _target(args.url)
            if not 1 <= args.timeout <= 30:
                raise SessionInputError('timeout must be an integer from 1 to 30 seconds')
            if args.output:
                descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                output = os.fdopen(descriptor, 'w', encoding='utf-8')
            summary = probe_session(args.url, timeout=args.timeout)
        elif args.command == 'probe-many':
            inputs = load_json(args.targets)
            validate_targets(inputs, timeout=args.timeout, max_seconds=args.max_seconds)
            if args.output:
                descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                output = os.fdopen(descriptor, 'w', encoding='utf-8')
            summary = probe_many(inputs, timeout=args.timeout, max_seconds=args.max_seconds)
        else:
            summary = compare_reports(load_json(args.left), load_json(args.right))
            if args.output:
                descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                output = os.fdopen(descriptor, 'w', encoding='utf-8')
    except (RecordError, SessionInputError, UnicodeError, OSError) as exc:
        if output is not None:
            output.close()
        command = args.command if 'args' in locals() else None
        code = 'invalid_record' if command == 'summarize' else 'invalid_input'
        next_step = {
            'summarize': 'Use a complete frozen native SDK record. See summarize --help.',
            'probe': 'Use a literal-loopback MCP URL and a new writable output path. See probe --help.',
            'probe-many': 'Use a schema-version-1 targets object with safe labels and literal-loopback URLs, and a new writable output path. See probe-many --help.',
            'compare': 'Use two saved probe or endpoint-set reports and a new writable output path. See compare --help.',
        }.get(command, 'Choose summarize, probe, probe-many or compare. See --help.')
        print(json.dumps({'requestID': request_id, 'error': {'code': code,
              'message': str(exc) if isinstance(exc, (RecordError, SessionInputError)) else 'Input or new output file is inaccessible or already exists.',
              'next_step': next_step}}),
              file=sys.stderr)
        return 2
    serialized = json.dumps({'requestID': request_id, **summary}, indent=2) + '\n'
    if output is not None:
        try:
            with output:
                output.write(serialized)
        except OSError:
            print(json.dumps({'requestID': request_id, 'error': {'code': 'output_failed',
                  'message': 'Cannot finish writing the new report.',
                  'next_step': 'Check free space and permissions. Keep this partial attempt and retry with a new output path.'}}), file=sys.stderr)
            return 2
    else:
        print(serialized, end='')
    return 0 if args.command == 'compare' or summary['verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
