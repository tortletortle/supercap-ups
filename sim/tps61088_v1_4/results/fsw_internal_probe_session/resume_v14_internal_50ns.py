"""Resume post-processing only; never starts LTspice."""
import json
import shutil
import run_v14_internal as run

result = run.V14 / 'results/fsw_internal_probe_50ns'
meta = json.loads((result / 'environment.json').read_text(encoding='utf-8'))
meta['postprocess_recovery_note'] = (
    'Initial runner mistakenly parsed .save in a comment; LTspice had already exited 0. '
    'Corrected line-anchored .save check and analyzed the existing unchanged RAW; no rerun.'
)
shutil.copyfile(run.WORK / 'run_v14_internal.py', run.SESSION / 'run_v14_internal.py')
run.postprocess(50, run.Path(meta['deck']), result, run.Path(meta['native_directory']), meta)
