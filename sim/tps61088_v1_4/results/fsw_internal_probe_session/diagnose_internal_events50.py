"""Read-only diagnostic of events the strict internal analyzer marks invalid."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from internal_probe_independent_check import WORK, NATIVE, RESULTS, open_raw, event_times, first, stats, value_at

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--step', type=int, choices=[50, 25], default=50)
step = parser.parse_args().step
result = RESULTS / f'fsw_internal_probe_{step}ns'
with (result / 'fsw_internal_cycles.csv').open(encoding='utf-8', newline='') as f:
    original = list(csv.DictReader(f))
path = NATIVE / f'freq_vin7_rfsw324k_internal_probe_{step}ns' / f'freq_vin7_rfsw324k_internal_probe_{step}ns.raw'
raw, idx, _ = open_raw(path)
try:
    def copy(name):
        return np.array(raw[:, idx[name]], dtype=float, copy=True)
    time = copy('time')
    delta = copy('v(x1:u5_n01584)') - copy('v(x1:u5_pvin)')
    comparator = copy('v(x1:u5_n16903113)')
    toff = copy('v(x1:u5_toff)')
    gate = copy('v(x1:gate_l)')
    sw = copy('v(sw)')
    events = {
        'cap_cross': event_times(time, delta, 0),
        'comp_rise': event_times(time, comparator, .5),
        'toff_rise': event_times(time, toff, .5),
        'gate_0p2': event_times(time, gate, .2),
        'gate_0p5': event_times(time, gate, .5),
        'gate_0p8': event_times(time, gate, .8),
        'sw_fall': event_times(time, sw, 10, False),
    }
    rows = []
    for r in original:
        if not r['next_cycle_start_s']:
            continue
        lo, hi = float(r['cycle_start_s']), float(r['next_cycle_start_s'])
        picked = {k: first(arr, lo, hi) for k, arr in events.items()}
        row = {'cycle_start_s': lo, 'source_status': r['cycle_status'], 'source_reason': r['invalid_reason']}
        row.update({key + '_count': int(np.searchsorted(arr, hi) - np.searchsorted(arr, lo)) for key, arr in events.items()})
        row.update({key + '_s': value for key, value in picked.items()})
        cap = picked['cap_cross']
        if cap is not None:
            for key, value in picked.items():
                row[key + '_minus_cap_ns'] = None if value is None else (value - cap) * 1e9
            j = int(np.searchsorted(time, cap))
            row['cap_cross_bracket_dt_ns'] = float((time[j] - time[j-1]) * 1e9)
            row['comp_at_cap_cross_V'] = value_at(time, comparator, cap)
            pred = float(r['rc_ode_predicted_cross_s']) if r['rc_ode_predicted_cross_s'] else None
            row['predicted_cross_s'] = pred
            row['predicted_to_gate_0p2_ns'] = None if pred is None or picked['gate_0p2'] is None else (picked['gate_0p2'] - pred)*1e9
        rows.append(row)
    fields = sorted({key for r in rows for key in r})
    out_csv = WORK / f'internal_probe_{step}ns_unfiltered_events.csv'
    with out_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    offsets = [r['comp_rise_minus_cap_ns'] for r in rows if r.get('comp_rise_minus_cap_ns') is not None]
    negative = [r for r in rows if r.get('comp_rise_minus_cap_ns') is not None and r['comp_rise_minus_cap_ns'] < 0]
    missing_comp = [r for r in rows if r['comp_rise_count'] != 1]
    sample_rows = [min(rows, key=lambda r: r.get('comp_rise_minus_cap_ns', np.inf)),
                   max(rows, key=lambda r: r.get('comp_rise_minus_cap_ns', -np.inf)), rows[1]]
    neighborhoods = []
    for r in sample_rows:
        cap = r['cap_cross_s']
        j = int(np.searchsorted(time, cap))
        neighborhoods.append({'events': r, 'stored_samples_near_cap_cross': [
            {'time_s': float(time[k]), 'relative_to_cap_ns': float((time[k]-cap)*1e9),
             'cap_minus_pvin_V': float(delta[k]), 'comparator_out_V': float(comparator[k]),
             'toff_V': float(toff[k]), 'gate_l_V': float(gate[k])}
            for k in range(max(0,j-4), min(len(time),j+5))]})
    data = {
        'max_step_ns': step, 'raw': str(path), 'full_cycles': len(rows),
        'source_invalid_cycles': sum(r['source_status'] == 'invalid' for r in rows),
        'all_events_single_in_full_cycle': {key: all(r[key+'_count'] == 1 for r in rows) for key in events},
        'comp_cross_precedes_interpolated_cap_cross_count': len(negative),
        'source_invalid_exactly_matches_comp_before_cap': all((r['source_status'] == 'invalid') == (r.get('comp_rise_minus_cap_ns', 1) < 0) for r in rows),
        'comp_minus_cap_ns': stats(offsets),
        'cap_cross_bracket_dt_ns': stats([r['cap_cross_bracket_dt_ns'] for r in rows]),
        'comp_at_cap_cross_V': stats([r['comp_at_cap_cross_V'] for r in rows]),
        'gate_0p2_minus_cap_ns': stats([r['gate_0p2_minus_cap_ns'] for r in rows]),
        'predicted_to_gate_0p2_ns': stats([r['predicted_to_gate_0p2_ns'] for r in rows if r['predicted_to_gate_0p2_ns'] is not None]),
        'toff_minus_cap_ns': stats([r['toff_rise_minus_cap_ns'] for r in rows]),
        'comp_to_toff_ns': stats([(r['toff_rise_s']-r['comp_rise_s'])*1e9 for r in rows]),
        'cap_to_sw_fall_ns': stats([r['sw_fall_minus_cap_ns'] for r in rows]),
        'neighborhoods': neighborhoods,
        'interpretation': 'Supplementary observation only. Original strict CSV/summary remain unchanged. Negative comparator-vs-interpolated-cap order is a sampled event ordering issue, not evidence by itself of a causal model defect.'
    }
    out_json = WORK / f'internal_probe_{step}ns_event_diagnosis.json'
    out_json.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k != 'neighborhoods'}, indent=2))
finally:
    raw._mmap.close()
