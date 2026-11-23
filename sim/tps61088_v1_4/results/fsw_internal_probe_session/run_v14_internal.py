"""Run one of the two authorized, unchanged LTspice internal-node probes."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent
REPO = WORK / 'supercap-ups-repo'
V14 = REPO / 'sim/tps61088_v1_4'
NATIVE_ROOT = WORK / 'v14-internal-native'
PREFLIGHT = WORK / 'v14-internal-preflight'
SESSION = V14 / 'results/fsw_internal_probe_session'
EXE = Path('C:/Users/tortl/AppData/Local/Programs/ADI/LTspice/LTspice.exe')
MODEL = REPO / 'sim/tps61088_v1_3/model/TPS61088_LT.LIB'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def postprocess(step, deck, result, native, metadata):
    if metadata['exit_code'] != 0 or sha(deck) != metadata['deck_sha256']:
        raise RuntimeError('Cannot resume analysis of an unsuccessful or changed deck')
    sys.path.insert(0, str(V14 / 'scripts'))
    from ltspice_raw import load_raw
    raw_path = native / (deck.stem + '.raw')
    header, names, raw = load_raw(raw_path)
    try:
        t = raw[:, 0]
        if abs(float(t[-1]) - 0.026) > 1e-12:
            raise RuntimeError('RAW does not reach 26 ms')
        save_line = next(line.strip() for line in deck.read_text(encoding='ascii').splitlines()
                         if line.strip().lower().startswith('.save '))
        actual = {n.lower() for n in names}
        missing = [s for s in save_line.split()[1:] if s.lower() not in actual]
        if missing:
            raise RuntimeError('Missing requested saved vectors: ' + ', '.join(missing))
        metadata['raw_validation'] = {'points': int(len(t)), 'variables': names,
                                      'start_s': float(t[0]), 'end_s': float(t[-1]),
                                      'complete_interleaved_double': True}
        (result / 'raw_header.txt').write_text(header, encoding='utf-8')
    finally:
        del t
        raw._mmap.close()
    dump(result / 'environment.json', metadata)
    command = ['py', '-3', 'sim/tps61088_v1_4/scripts/analyze_fsw_internal.py',
               '--raw', str(raw_path), '--out', str(result), '--max-step-ns', str(step)]
    if step == 25:
        command += ['--compare-with', 'sim/tps61088_v1_4/results/fsw_internal_probe_50ns/fsw_internal_summary.json']
    metadata['analysis_command'] = command
    metadata['analysis_script_sha256_at_analysis'] = sha(V14 / 'scripts/analyze_fsw_internal.py')
    env = os.environ | {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8'}
    with (result / 'analysis_stdout.json').open('wb') as out, (result / 'analysis_stderr.txt').open('wb') as err:
        analyzed = subprocess.run(command, cwd=REPO, env=env, stdout=out, stderr=err)
    metadata['analysis_exit_code'] = analyzed.returncode
    dump(result / 'environment.json', metadata)
    if analyzed.returncode:
        raise RuntimeError('Analyzer failed; see preserved stderr')
    print(f'FINISHED {deck.stem}: LTspice exit={metadata["exit_code"]}, analysis exit={analyzed.returncode}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--step', type=int, choices=(50, 25), required=True)
    args = parser.parse_args()
    step = args.step
    case_name = f'freq_vin7_rfsw324k_internal_probe_{step}ns'
    deck = V14 / 'diagnostics' / (case_name + '.cir')
    result = V14 / 'results' / f'fsw_internal_probe_{step}ns'
    native = NATIVE_ROOT / case_name
    if result.exists() or native.exists():
        raise RuntimeError('Previous evidence exists; refusing overwrite')
    if step == 25:
        base_env = json.loads((V14 / 'results/fsw_internal_probe_50ns/environment.json').read_text(encoding='utf-8'))
        if base_env.get('exit_code') != 0 or not base_env.get('raw_validation', {}).get('complete_interleaved_double'):
            raise RuntimeError('50 ns simulation and complete-RAW checks must finish first')
    if sha(EXE) != '3c144a2b3ec6a30baac6761c502d99b95aaa40b947ff5eca25b8fbd80d68af72':
        raise RuntimeError('LTspice differs from original baseline')
    if sha(MODEL) != '418466fbd205f9e9ec487bee1d9c1ada48858ff49eef67767e84706966fa1795':
        raise RuntimeError('Model differs from original baseline')
    if git('diff', 'HEAD', '--', str(deck), str(MODEL)):
        raise RuntimeError('Deck or model has uncommitted changes')
    deck_text = deck.read_text(encoding='ascii')
    for expected in (
        '.options method=gear reltol=.003 trtol=7 gmin=1e-10 numdgt=7 threads=1 plotwinsize=0',
        f'.tran 0 26m 0 {step}n', 'RFSW fsw sw 324k', 'RILIM ilim 0 100k',
        'L1 vin sw 3.3u Rser=0.026',
        'X1 0 boot comp en fb fsw ilim 0 nc0 nc1 0 ss sw sw sw sw vcc vin vout vout vout TPS61088_TRANS',
        '.meas tran sw_t6001 WHEN V(sw)=10 RISE=6001',
        '.meas tran sw_t6101 WHEN V(sw)=10 RISE=6101',
    ):
        if expected not in deck_text:
            raise RuntimeError('Preflight failed: ' + expected)
    if any(p != deck for p in deck.parent.glob(case_name + '.*')):
        raise RuntimeError('Native result already exists alongside deck')
    SESSION.mkdir(exist_ok=True)
    if step == 50:
        env = os.environ | {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8'}
        tests = subprocess.run(['py', '-3', '-m', 'unittest', 'discover', '-s',
                                'sim/tps61088_v1_4/tests', '-v'], cwd=REPO, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (SESSION / 'unit_tests_after.log').write_bytes(tests.stdout)
        for p in PREFLIGHT.glob('*.log'):
            shutil.copyfile(p, SESSION / p.name)
        if tests.returncode:
            raise RuntimeError('Unit tests failed')
        (SESSION / 'analysis_fix.diff').write_bytes(subprocess.check_output(
            ['git', 'diff', '--', 'sim/tps61088_v1_4/scripts/analyze_fsw_internal.py',
             'sim/tps61088_v1_4/tests/test_fsw_internal.py'], cwd=REPO))
        shutil.copyfile(Path(__file__), SESSION / Path(__file__).name)
    result.mkdir()
    native.mkdir(parents=True)
    shutil.copyfile(deck, result / 'input_deck.cir.txt')
    metadata = {
        'source_commit': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
        'source_worktree_status': git('status', '--porcelain'),
        'os': platform.platform(), 'python': sys.version,
        'simulator_path': str(EXE), 'simulator_version': '26.1.1.0',
        'simulator_sha256': sha(EXE), 'model_path': str(MODEL), 'model_sha256': sha(MODEL),
        'model_version': 'TI ordinary TPS61088 Final 1.00 / 11MAY2015, compatibility expression edits retained',
        'deck': str(deck), 'deck_sha256': sha(deck), 'max_step_ns': step,
        'native_directory': str(native), 'started_utc': now(),
        'command': [str(EXE), '-b', str(deck)], 'cwd': str(deck.parent),
        'solver_expected': 'Normal / Gear',
        'analysis_script_sha256': sha(V14 / 'scripts/analyze_fsw_internal.py'),
        'raw_reader_sha256': sha(V14 / 'scripts/ltspice_raw.py'),
    }
    dump(result / 'environment.json', metadata)
    started = time.monotonic()
    with (result / 'runner_stdout.txt').open('wb') as out, (result / 'runner_stderr.txt').open('wb') as err:
        proc = subprocess.Popen(metadata['command'], cwd=deck.parent, stdout=out, stderr=err,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        metadata['pid'] = proc.pid
        dump(result / 'environment.json', metadata)
        print(f'START {case_name} PID={proc.pid}', flush=True)
        while proc.poll() is None:
            time.sleep(10)
            raw = deck.with_suffix('.raw')
            print(f'{case_name} elapsed={time.monotonic()-started:.0f}s raw_bytes={raw.stat().st_size if raw.exists() else 0}', flush=True)
    metadata.update(finished_utc=now(), elapsed_wall_s=round(time.monotonic() - started, 3),
                    exit_code=proc.returncode, deck_sha256_after_run=sha(deck))
    if metadata['deck_sha256'] != metadata['deck_sha256_after_run']:
        raise RuntimeError('Deck changed during simulation')
    if deck.with_suffix('.log').exists():
        shutil.copyfile(deck.with_suffix('.log'), result / 'ltspice_original.log')
    for file in deck.parent.glob(case_name + '.*'):
        if file != deck:
            shutil.move(str(file), native / file.name)
    metadata['native_files'] = [
        {'name': f.name, 'bytes': f.stat().st_size, 'sha256': sha(f)}
        for f in sorted(native.iterdir())
    ]
    dump(result / 'environment.json', metadata)
    if proc.returncode:
        raise RuntimeError('LTspice exited nonzero; original evidence retained')
    postprocess(step, deck, result, native, metadata)


if __name__ == '__main__':
    main()
