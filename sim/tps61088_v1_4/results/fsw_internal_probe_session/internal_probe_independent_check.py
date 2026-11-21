"""Independent, read-only checks for the two actual FSW probe experiments.

Does not import any repository simulation/analysis code or launch LTspice.
Only writes this checker's JSON report under work/.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np

WORK = Path(__file__).resolve().parent
REPO = WORK / 'supercap-ups-repo'
RESULTS = REPO / 'sim/tps61088_v1_4/results'
NATIVE = WORK / 'v14-internal-native'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def open_raw(path):
    """Parse the UTF-16 header independently, then validate the exact payload."""
    with path.open('rb') as f:
        prefix = f.read(65536)
    markers = ['Binary:\n'.encode('utf-16le'), 'Binary:\r\n'.encode('utf-16le')]
    offsets = [prefix.find(m) + len(m) for m in markers if prefix.find(m) >= 0]
    if not offsets:
        raise ValueError('No UTF-16 binary marker in ' + str(path))
    offset = min(offsets)
    header = prefix[:offset].decode('utf-16le')
    def field(label):
        return re.search(r'^' + re.escape(label) + r':\s*([^\r\n]+)', header, re.M).group(1)
    count = int(field('No. Points'))
    width = int(field('No. Variables'))
    flags = field('Flags').lower()
    names = re.findall(r'^\s*\d+\t([^\t\r\n]+)\t[^\r\n]+', header, re.M)
    assert 'double' in flags and 'fastaccess' not in flags, flags
    assert len(names) == width
    assert path.stat().st_size == offset + count * width * 8, 'Incomplete binary payload'
    raw = np.memmap(path, dtype='<f8', mode='r', offset=offset, shape=(count, width))
    return raw, {name.lower(): i for i, name in enumerate(names)}, names


def event_times(time, values, threshold, rising=True):
    """Independent linear interpolation across all sampled level transitions."""
    over = (values >= threshold).astype(np.int8)
    transitions = np.diff(over)
    indices = np.nonzero(transitions == (1 if rising else -1))[0]
    dt = time[indices + 1] - time[indices]
    keep = dt > 0
    indices, dt = indices[keep], dt[keep]
    return time[indices] + dt * ((threshold - values[indices]) /
                                (values[indices + 1] - values[indices]))


def first(events, lo, hi):
    k = int(np.searchsorted(events, lo))
    return float(events[k]) if k < len(events) and events[k] < hi else None


def value_at(time, values, when):
    k = int(np.searchsorted(time, when))
    if k == 0:
        return float(values[0])
    if k == len(time):
        return float(values[-1])
    fraction = (when - time[k-1]) / (time[k] - time[k-1])
    return float(values[k-1] + fraction * (values[k] - values[k-1]))


def stats(values, scale=1.0):
    x = np.asarray(values, dtype=float) * scale
    return {'count': int(len(x)), 'min': float(np.min(x)),
            'median': float(np.median(x)), 'max': float(np.max(x)),
            'p05': float(np.percentile(x, 5)), 'p95': float(np.percentile(x, 95))} if len(x) else None


def read_log(path):
    payload = path.read_bytes()
    text = payload.decode('utf-16') if payload.startswith((b'\xff\xfe', b'\xfe\xff')) else payload.decode('utf-8-sig')
    measurements = {}
    for label in ['t90', 't98', 'sw_t6001', 'sw_t6101', 'f_sw_khz', 'avg_vout',
                  'ripple', 'peak_i', 'peak_start', 'iout_avg', 'eta_pct']:
        line = re.search(r'^' + label + r':([^\r\n]+)', text, re.M)
        if line:
            match = re.search(r'(?: AT |=)([-+\d.eE]+)(?: FROM |$)', line.group(1))
            if match:
                measurements[label] = float(match.group(1))
    return text, measurements


def check_case(step):
    name = f'freq_vin7_rfsw324k_internal_probe_{step}ns'
    result = RESULTS / f'fsw_internal_probe_{step}ns'
    path = NATIVE / name / (name + '.raw')
    # Never inspect an in-progress simulation: runner emits summary only after exit.
    summary = json.loads((result / 'fsw_internal_summary.json').read_text(encoding='utf-8'))
    environment = json.loads((result / 'environment.json').read_text(encoding='utf-8'))
    assert environment['exit_code'] == 0 and environment['analysis_exit_code'] == 0
    with (result / 'fsw_internal_cycles.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    log, measured = read_log(result / 'ltspice_original.log')
    raw, idx, names = open_raw(path)
    checks = {}
    try:
        native_hashes = {item['name']: item['sha256'] for item in environment['native_files']}
        raw_digest = sha(path)
        checks['raw_sha256_matches_environment'] = raw_digest == native_hashes[path.name]
        checks['original_log_sha256_matches_native'] = sha(result / 'ltspice_original.log') == native_hashes[name + '.log']
        def v(name):
            return np.asarray(raw[:, idx[name]])
        time = v('time')
        checks['time_monotonic_and_finite'] = bool(np.all(np.isfinite(time)) and np.all(np.diff(time) >= 0))
        checks['complete_26ms'] = abs(float(time[-1]) - .026) < 1e-15
        checks['point_count_matches_summary'] = len(time) == summary['raw_point_count']
        checks['all_requested_nodes_present'] = all(s.lower() in idx for s in environment['raw_validation']['variables'])
        rises = event_times(time, v('v(sw)'), 10)
        falls = event_times(time, v('v(sw)'), 10, False)
        t98 = float(event_times(time, v('v(vout)'), 11.76)[0])
        t6001, t6101 = float(rises[6000]), float(rises[6100])
        freq = .1 / (t6101 - t6001)
        derived = {'t98': t98, 'sw_t6001': t6001, 'sw_t6101': t6101, 'f_sw_khz': freq}
        checks['raw_log_timing_matches'] = all(abs(derived[k] - measured[k]) <= (1e-7 if k == 'f_sw_khz' else 1e-12) for k in derived)
        checks['original_timing_valid'] = t98 < t6001 < t6101 < .026
        prescribed = summary['prescribed_edge_measurement']
        checks['raw_summary_frequency_matches'] = abs(freq - prescribed['frequency_kHz']) < 1e-9
        checks['raw_summary_edge_count_matches'] = len(rises) == prescribed['raw_10V_rise_count']
        checks['summary_timing_valid_matches'] = bool(prescribed['timing_valid']) == checks['original_timing_valid']
        counts = Counter(r['cycle_status'] for r in rows)
        valid = [r for r in rows if r['cycle_valid'] == 'True']
        counted = {'candidate_cycles': len(rows), 'complete_valid_cycles': len(valid),
                   'right_censored_cycles': counts['right_censored_at_raw_end'],
                   'invalid_cycles': counts['invalid']}
        checks['csv_cycle_counts_match_summary'] = counted == summary['cycle_accounting']
        events = {
            'pvin_cross': event_times(time, v('v(x1:u5_n01584)') - v('v(x1:u5_pvin)'), 0),
            'comparator_rise': event_times(time, v('v(x1:u5_n16903113)'), .5),
            'toff_rise': event_times(time, v('v(x1:u5_toff)'), .5),
            'gate_rise_0p2': event_times(time, v('v(x1:gate_l)'), .2),
            'gate_rise_0p5': event_times(time, v('v(x1:gate_l)'), .5),
            'gate_rise_0p8': event_times(time, v('v(x1:gate_l)'), .8),
            'cap_reset_fall': event_times(time, v('v(x1:u5_n01584)'), .5, False),
            'sw_fall': falls,
        }
        count_histograms = {key: Counter() for key in events}
        ordered_count = 0
        csv_event_match_count = 0
        actual_to_gate = {key: [] for key in ['gate_rise_0p2', 'gate_rise_0p5', 'gate_rise_0p8']}
        predicted_to_gate = {key: [] for key in actual_to_gate}
        actual_gate_values = []
        predicted_gate_values = []
        map_csv = {'pvin_cross': 'pvin_cross_s', 'comparator_rise': 'comparator_output_rise_s',
                   'toff_rise': 'u5_toff_0p5V_rise_s', 'gate_rise_0p5': 'gate_l_rise_s',
                   'cap_reset_fall': 'cap_reset_0p5V_fall_s', 'sw_fall': 'sw_fall_10V_s'}
        order = ['pvin_cross', 'comparator_rise', 'toff_rise', 'gate_rise_0p5',
                 'cap_reset_fall', 'sw_fall']
        for row in valid:
            lo, hi = float(row['cycle_start_s']), float(row['next_cycle_start_s'])
            chosen = {}
            for key, arr in events.items():
                n = int(np.searchsorted(arr, hi) - np.searchsorted(arr, lo))
                count_histograms[key][n] += 1
                chosen[key] = first(arr, lo, hi)
            seq = [chosen[key] for key in order]
            if all(x is not None for x in seq) and all(a <= b + 1e-15 for a, b in zip(seq, seq[1:])):
                ordered_count += 1
            if all(chosen[key] is not None and abs(chosen[key] - float(row[col])) < 1e-14 for key, col in map_csv.items()):
                csv_event_match_count += 1
            crossing = chosen['pvin_cross']
            predicted = float(row['rc_ode_predicted_cross_s']) if row['rc_ode_predicted_cross_s'] else None
            if crossing is not None:
                actual_gate_values.append(value_at(time, v('v(x1:gate_l)'), crossing))
                for key in actual_to_gate:
                    if chosen[key] is not None:
                        actual_to_gate[key].append(chosen[key] - crossing)
            if predicted is not None:
                predicted_gate_values.append(value_at(time, v('v(x1:gate_l)'), predicted))
                for key in predicted_to_gate:
                    if chosen[key] is not None:
                        predicted_to_gate[key].append(chosen[key] - predicted)
        checks['all_valid_cycles_event_order_confirmed'] = ordered_count == len(valid)
        checks['all_valid_cycles_csv_event_times_confirmed'] = csv_event_match_count == len(valid)
        checks['all_internal_events_single_per_valid_cycle'] = all(dict(hist) == {1: len(valid)} for hist in count_histograms.values())
        checks['actual_cross_before_gate_0p2'] = bool(actual_to_gate['gate_rise_0p2']) and min(actual_to_gate['gate_rise_0p2']) > 0
        checks['predicted_cross_before_gate_0p2'] = bool(predicted_to_gate['gate_rise_0p2']) and min(predicted_to_gate['gate_rise_0p2']) > 0
        comparison = None
        if step == 50:
            base_path = WORK / 'v14-first-case-native/freq_vin7_rfsw324k.raw'
            baseline, bi, bn = open_raw(base_path)
            try:
                common = sorted(set(idx) & set(bi))
                vector_records = []
                for key in common:
                    equal = baseline.shape[0] == raw.shape[0]
                    max_abs = 0.0
                    if equal:
                        for start in range(0, len(raw), 200000):
                            a = raw[start:start+200000, idx[key]]
                            b = baseline[start:start+200000, bi[key]]
                            equal = equal and bool(np.array_equal(a, b))
                            max_abs = max(max_abs, float(np.max(np.abs(a - b))))
                    vector_records.append({'vector': key, 'all_samples_equal': equal, 'max_abs_difference': max_abs if baseline.shape[0] == raw.shape[0] else None})
                comparison = {'baseline_raw': str(base_path), 'baseline_point_count': int(len(baseline)),
                              'common_vector_count': len(common), 'baseline_vector_count': len(bn),
                              'vectors': vector_records}
                checks['baseline_common_raw_samples_identical'] = bool(common) and all(r['all_samples_equal'] for r in vector_records)
            finally:
                baseline._mmap.close()
        result_data = {
            'case_max_step_ns': step, 'raw_path': str(path), 'raw_bytes': path.stat().st_size,
            'raw_sha256': raw_digest, 'raw_points': int(len(time)), 'raw_variables': names,
            'end_time_s': float(time[-1]), 'raw_10V_rise_count': int(len(rises)),
            'independent_measurements': derived, 'log_measurements': measured,
            'csv_cycle_counts': counted, 'checks': checks,
            'all_checks_pass': all(checks.values()),
            'internal_event_counts_per_valid_cycle': {key: dict(hist) for key, hist in count_histograms.items()},
            'actual_pvin_cross_to_gate_ns': {key: stats(value, 1e9) for key, value in actual_to_gate.items()},
            'predicted_rc_cross_to_gate_ns': {key: stats(value, 1e9) for key, value in predicted_to_gate.items()},
            'gate_voltage_at_actual_cross_V': stats(actual_gate_values),
            'gate_voltage_at_predicted_cross_V': stats(predicted_gate_values),
            'baseline_raw_comparison': comparison,
            'model_emission_coefficient_warning_count': log.count('Emission coefficient'),
            'log_records_normal_gear': 'solver = Normal' in log and 'method = Gear' in log,
            'interpretation': 'Checks verify sampled macro-model data, not silicon behavior or hardware efficiency.'
        }
        return result_data
    finally:
        raw._mmap.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['50', '25', 'all'], default='all')
    args = parser.parse_args()
    cases = [50, 25] if args.case == 'all' else [int(args.case)]
    checks = [check_case(step) for step in cases]
    result = {'checker_sha256': sha(Path(__file__)), 'verified_utc': datetime.now(timezone.utc).isoformat(),
              'method': 'Independent RAW header/payload validation, own transition interpolation, own internal-event counts; no analyzer imports.',
              'cases': checks}
    if args.case == 'all':
        actual = json.loads((RESULTS / 'fsw_internal_probe_25ns/fsw_internal_comparison.json').read_text(encoding='utf-8'))
        delta = checks[1]['independent_measurements']['f_sw_khz'] - checks[0]['independent_measurements']['f_sw_khz']
        result['comparison_delta_khz_expected'] = delta
        result['comparison_delta_khz_recorded'] = actual['frequency_delta_khz']
        result['comparison_frequency_delta_matches'] = abs(delta - actual['frequency_delta_khz']) < 1e-9
    result['all_checks_pass'] = all(c['all_checks_pass'] for c in checks) and result.get('comparison_frequency_delta_matches', True)
    suffix = '' if args.case == 'all' else '_' + args.case + 'ns'
    out = WORK / ('internal_probe_independent_check' + suffix + '.json')
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'all_checks_pass': result['all_checks_pass'],
                      'cases': [{'max_step_ns': c['case_max_step_ns'], 'frequency_khz': c['independent_measurements']['f_sw_khz'],
                                 'checks': c['checks']} for c in checks]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
