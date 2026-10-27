"""Exercise an sdist and its clean wheel outside the source checkout."""
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


def run(command, **kwargs):
    subprocess.run(command, check=True, timeout=180, **kwargs)


def main():
    scratch = Path(sys.argv[1]).resolve()
    archive = next((scratch / 'dist').glob('*.tar.gz'))
    with tarfile.open(archive) as bundle:
        names = bundle.getnames()
        for required in ['tests/sdk/python_server.py', 'tests/sdk/typescript_server.mjs',
                         'tests/sdk/uv.lock', 'tests/sdk/package-lock.json',
                         'tests/sdk/gate.py', 'scripts/verify-release.sh', 'docs/USAGE.md']:
            assert any(name.endswith('/' + required) for name in names), required
        assert not any('LICENSE-STATUS' in name or '/node_modules/' in name for name in names)
        for required in ['src/mcp_connect_diagnoser/session_probe.py',
                         'src/mcp_connect_diagnoser/reports.py', 'tests/test_additions.py',
                         'tests/test_session_probe.py', 'tests/test_catalogue.py', 'tests/sdk/session_server.py',
                         'scripts/verify_session.py', 'tests/test_quickstart.py',
                         'examples/quickstart.py', 'docs/STABILITY.md', 'docs/RELEASING.md',
                         'docs/images/session-workflow.svg', 'CHANGELOG.md',
                         'tests/sdk/ping_metadata_server.py', 'scripts/verify_ping_metadata.py',
                         'docs/COMPATIBILITY.md', 'tests/test_loopback_startup.py',
                         'tests/test_resume_encoding.py']:
            assert any(name.endswith('/' + required) for name in names), required
        bundle.extractall(scratch / 'source', filter='data')
    source = next((scratch / 'source').iterdir())
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    run(['uv', 'build', str(source), '--wheel', '--python', sys.executable,
         '--build-constraints', str(source / 'requirements-release.txt'),
         '--out-dir', str(scratch / 'rebuilt')], env=env)
    wheel = next((scratch / 'rebuilt').glob('*.whl'))
    with zipfile.ZipFile(wheel) as bundle:
        assert not any('LICENSE-STATUS' in name for name in bundle.namelist())
        wheel_files = bundle.namelist()
        assert 'mcp_connect_diagnoser/reports.py' in wheel_files
    venv = scratch / 'wheel-env'
    run(['uv', 'venv', '--python', sys.executable, str(venv)], env=env)
    python = venv / 'bin/python'
    run(['uv', 'pip', 'install', '--python', str(python), '--no-deps', str(wheel)], env=env)
    # cwd has no source package; imports must come from the installed wheel.
    env['PYTHONPATH'] = str(source / 'tests')
    run([str(python), '-m', 'unittest', 'discover', '-s', str(source / 'tests'), '-v'], cwd=scratch, env=env)
    import_result = subprocess.check_output([str(python), '-c',
        'import mcp_connect_diagnoser; from importlib.metadata import version; assert mcp_connect_diagnoser.__version__ == version("mcp-connect-diagnoser") == "1.0.2"; print(mcp_connect_diagnoser.__file__)'], cwd=scratch, env=env, timeout=10).decode().strip()
    assert str(venv) in import_result, import_result
    sample = subprocess.check_output([str(python), '-c',
        'import json; from test_native_records import record_fixture; print(json.dumps(record_fixture()))'],
        cwd=scratch, env=env, timeout=10)
    sample_path = scratch / 'authored-record.json'
    sample_path.write_bytes(sample)
    summary = subprocess.check_output([str(venv / 'bin/mcp-connect-diagnoser'),
        'summarize', str(sample_path)], cwd=scratch, env=env, timeout=10)
    assert json.loads(summary)['verified'] is True
    receipt = {'wheel_import': import_result, 'wheel_files': wheel_files,
               'authored_sample': 'Schema/fidelity CLI smoke only, not SDK runtime evidence.',
               'sha256': {str(path.relative_to(scratch)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [archive, wheel, sample_path]}}
    (scratch / 'package-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
