"""Stage check: compare the completed 50 ns RAW with the original baseline."""
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from internal_probe_independent_check import open_raw, sha, WORK

baseline_path = WORK / 'v14-first-case-native/freq_vin7_rfsw324k.raw'
current_path = WORK / 'v14-internal-native/freq_vin7_rfsw324k_internal_probe_50ns/freq_vin7_rfsw324k_internal_probe_50ns.raw'
baseline, bi, bn = open_raw(baseline_path)
current, ci, cn = open_raw(current_path)
try:
    common = sorted(set(bi) & set(ci))
    records = []
    for name in common:
        same = len(current) == len(baseline)
        max_abs = 0.0
        if same:
            for start in range(0, len(current), 200000):
                a = current[start:start+200000, ci[name]]
                b = baseline[start:start+200000, bi[name]]
                same = same and bool(np.array_equal(a, b))
                max_abs = max(max_abs, float(np.max(np.abs(a-b))))
        records.append({'vector': name, 'all_samples_equal': same,
                        'max_abs_difference': max_abs if len(current) == len(baseline) else None})
    result = {'verified_utc': datetime.now(timezone.utc).isoformat(),
              'baseline_raw': str(baseline_path), 'baseline_raw_sha256': sha(baseline_path),
              'current_raw': str(current_path), 'current_raw_sha256': sha(current_path),
              'baseline_points': int(len(baseline)), 'current_points': int(len(current)),
              'baseline_variables': bn, 'current_variables': cn,
              'common_vector_count': len(common), 'baseline_vector_count': len(bn),
              'all_common_vectors_identical': all(r['all_samples_equal'] for r in records),
              'vectors': records}
    destination = WORK / 'internal_probe_baseline_equality_50ns.json'
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(destination), 'all_common_vectors_identical': result['all_common_vectors_identical'],
                      'common_vectors': len(common), 'points': len(current)}))
finally:
    baseline._mmap.close()
    current._mmap.close()
