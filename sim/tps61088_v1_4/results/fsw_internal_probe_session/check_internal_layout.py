"""Compare pre/post layout optimization without changing any circuit or event rule."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

WORK = Path(__file__).resolve().parent
REPO = WORK / 'supercap-ups-repo'
SCRIPTS = REPO / 'sim/tps61088_v1_4/scripts'
SESSION = REPO / 'sim/tps61088_v1_4/results/fsw_internal_probe_session'
RAW = WORK / 'v14-internal-native/freq_vin7_rfsw324k_internal_probe_50ns/freq_vin7_rfsw324k_internal_probe_50ns.raw'
ROOT = SESSION / 'layout_equivalence'
ROOT.mkdir(exist_ok=False)
env = os.environ | {'PYTHONPATH': str(SCRIPTS), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8'}
records = []
for label, source in [('before', SESSION / 'analyze_fsw_internal_before_contiguous.py'),
                      ('after', SCRIPTS / 'analyze_fsw_internal.py')]:
    output = ROOT / label
    output.mkdir()
    command = ['py', '-3', str(source), '--raw', str(RAW), '--out', str(output),
               '--start', '0.024', '--end', '0.02402', '--max-step-ns', '50']
    start = time.monotonic()
    with (output / 'stdout.json').open('wb') as stdout, (output / 'stderr.txt').open('wb') as stderr:
        result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr)
    assert result.returncode == 0, label
    records.append({'label': label, 'command': command, 'exit_code': result.returncode,
                    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                    'elapsed_wall_s': time.monotonic() - start})
checks = {}
for name in ('fsw_internal_summary.json', 'fsw_internal_cycles.csv'):
    before = (ROOT / 'before' / name).read_bytes()
    after = (ROOT / 'after' / name).read_bytes()
    checks[name] = {'byte_equal': before == after, 'sha256': hashlib.sha256(after).hexdigest()}
assert all(c['byte_equal'] for c in checks.values())
report = {'method': 'Same stored double samples and unchanged algorithm; only column contiguity differs.',
          'window_s': [0.024, 0.02402], 'raw_path': str(RAW), 'runs': records, 'output_checks': checks,
          'scope_limit': 'Equivalence comparison covers this diagnostic window; final deliverables use full 24-26ms window.'}
(ROOT / 'equivalence.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
