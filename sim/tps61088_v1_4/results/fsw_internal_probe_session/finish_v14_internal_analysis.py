"""Retain prior attempts and run only read-only analysis on existing RAWs."""
import json
from pathlib import Path
import shutil
import run_v14_internal as run

records = []
for step in (50, 25):
    result = run.V14 / f'results/fsw_internal_probe_{step}ns'
    prior = run.SESSION / 'analysis_prior_attempts' / f'{step}ns'
    prior.mkdir(parents=True, exist_ok=False)
    for name in ('environment.json', 'analysis_stdout.json', 'analysis_stderr.txt'):
        shutil.copyfile(result / name, prior / name)
    meta = json.loads((result / 'environment.json').read_text(encoding='utf-8'))
    meta['prior_analysis_note'] = (
        'Read-only slow analyzer manually stopped after storage-layout optimization; circuit simulation succeeded.'
        if step == 50 else
        'Initial comparison failed because baseline summary was not ready; circuit simulation and own summary/CSV succeeded.'
    )
    run.postprocess(step, Path(meta['deck']), result, Path(meta['native_directory']), meta)
    records.append({'max_step_ns': step, 'prior_attempt': str(prior),
                    'final_analysis_source_sha256': run.sha(run.V14 / 'scripts/analyze_fsw_internal.py')})
for name in ('fsw_internal_summary.json', 'fsw_internal_cycles.csv'):
    a = run.WORK / 'v14-internal-contiguous-50ns' / name
    b = run.V14 / 'results/fsw_internal_probe_50ns' / name
    assert a.read_bytes() == b.read_bytes(), name
run.dump(run.SESSION / 'analysis_recovery.json', {
    'cases': records, 'same_optimized_analyzer_repeat_50ns_byte_identical': True,
    'note': 'Both final commands used full RAW and prescribed default window/edges. No LTspice rerun.'})
print('Both final prescribed analysis commands completed.', flush=True)
