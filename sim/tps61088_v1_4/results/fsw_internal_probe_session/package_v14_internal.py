"""Build review tables/plots from the two completed native experiments."""
import csv
import json
from pathlib import Path
import re
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

WORK = Path(__file__).resolve().parent
REPO = WORK / 'supercap-ups-repo'
V14 = REPO / 'sim/tps61088_v1_4'
SESSION = V14 / 'results/fsw_internal_probe_session'
sys.path.insert(0, str(V14 / 'scripts'))
from ltspice_raw import load_raw


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    inventory, measures, plot_windows = [], [], []
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    colors = {50: '#0072B2', 25: '#D55E00'}
    summaries = {}
    for step in (50, 25):
        root = V14 / 'results' / f'fsw_internal_probe_{step}ns'
        env = json.loads((root / 'environment.json').read_text(encoding='utf-8'))
        result = json.loads((root / 'fsw_internal_summary.json').read_text(encoding='utf-8'))
        summaries[str(step)] = result
        text = (root / 'ltspice_original.log').read_text(encoding='utf-8-sig')
        vals = {}
        for line in text.splitlines():
            match = re.match(r'^([A-Za-z][A-Za-z0-9_]*):\s*(.*)', line)
            if not match:
                continue
            key, body = match.groups()
            if key.lower() not in {'t90', 't98', 'sw_t6001', 'sw_t6101', 'f_sw_khz',
                                   'avg_vout', 'ripple', 'peak_i', 'peak_start',
                                   'iin_avg', 'iout_avg', 'pin_avg', 'pout_avg', 'eta_pct'}:
                continue
            value = re.search(r'\bAT\s+([-+0-9.eE]+)', body)
            if value is None:
                value = re.search(r'=\s*([-+0-9.eE]+)(?:\s|$)', body)
            if value is not None:
                vals[key.lower()] = float(value.group(1))
        measures.append({'max_step_ns': step, 'ltspice_exit_code': env['exit_code'], **vals,
                         'analysis_status': result['analysis_status'],
                         **result['cycle_accounting']})
        for f in env['native_files']:
            inventory.append({'max_step_ns': step, 'path': str(Path(env['native_directory']) / f['name']),
                              'bytes': f['bytes'], 'sha256': f['sha256']})
        rows = list(csv.DictReader((root / 'fsw_internal_cycles.csv').open(encoding='utf-8', newline='')))
        row = next(r for r in rows if r['cycle_valid'] == 'True' and float(r['cycle_start_s']) >= 0.0245)
        start, end = float(row['cycle_start_s']), float(row['next_cycle_start_s'])
        header, names, raw = load_raw(Path(result['raw_path']))
        try:
            idx = {n.lower(): i for i, n in enumerate(names)}
            t = raw[:, 0]
            a, b = np.searchsorted(t, [start - 20e-9, end + 20e-9])
            tt = (t[a:b] - start) * 1e6
            color = colors[step]
            def vec(n): return raw[a:b, idx[n]]
            axes[0, 0].plot(tt, vec('v(x1:u5_n01584)'), color=color, label=f'{step} ns cap')
            axes[0, 0].plot(tt, vec('v(x1:u5_pvin)'), color=color, linestyle='--', label=f'{step} ns PVIN')
            axes[0, 1].plot(tt, vec('v(sw)'), color=color, label=f'{step} ns')
            axes[1, 0].plot(tt, vec('v(x1:gate_l)'), color=color, label=f'{step} ns GATE_L')
            axes[1, 0].plot(tt, vec('v(x1:u5_toff)'), color=color, linestyle='--', label=f'{step} ns TOFF')
            axes[1, 1].plot(tt, vec('v(x1:u5_ifsw)') * 1e6, color=color, label=f'{step} ns internal IFSW')
            axes[1, 1].plot(tt, -vec('i(rfsw)') * 1e6, color=color, linestyle='--', label=f'{step} ns -I(RFSW)')
            plot_windows.append({'max_step_ns': step, 'raw_path': result['raw_path'],
                                 'cycle_start_s': start, 'next_cycle_start_s': end,
                                 'plotted_raw_index_start': int(a), 'plotted_raw_index_end_exclusive': int(b),
                                 'alignment': 'Each run aligned to its own first complete cycle after 24.5 ms; illustrative overlay only.'})
        finally:
            del t
            raw._mmap.close()
    for ax, title, unit in zip(axes.flat,
                              ['Timing capacitor and direct threshold', 'Switch node', 'Timing logic', 'Current-sense consistency'],
                              ['V', 'V', 'V', 'uA']):
        ax.set_title(title)
        ax.set_xlabel('Time from each run\'s SW rise (us)')
        ax.set_ylabel(unit)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle('TPS61088 internal probes: 50 ns / 25 ns Gear (actual LTspice RAW)')
    fig.savefig(SESSION / 'internal_timing_overlay.png', dpi=170)
    plt.close(fig)
    for name, rows in [('measurements.csv', measures), ('native_files_local_inventory.csv', inventory)]:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with (SESSION / name).open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    dump(SESSION / 'plot_windows.json', plot_windows)
    dump(SESSION / 'measurement_table.json', measures)
    print(json.dumps(measures, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
