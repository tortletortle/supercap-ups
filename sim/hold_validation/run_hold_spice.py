import argparse
import csv
import math
import re
import subprocess
from pathlib import Path

CASES = {
    'nominal': ([10.] * 4, [.075] * 4),
    'tol_-10%': ([9.] * 4, [.075] * 4),
    'stress_EOL': ([6.3] * 4, [.1125] * 4),
    'single_weak_cell': ([6.3, 9., 9., 9.], [.1125, .075, .075, .075]),
}
EFFICIENCIES = (.90, .92, .95)
START, PLOAD, PATH_EFF, CELL_MIN = 9.4, 12., .99, 1.


def deck(case, caps, esrs, eta):
    lines = [f'* DC V1.2 | {case} | boost eta={eta:g} | behavioral hold']
    nodes = ['0', 'n1', 'n2', 'n3', 'pack']
    for j, (bottom, top, c, r) in enumerate(zip(nodes[:-1], nodes[1:], caps, esrs), 1):
        lines += [f'C{j} p{j} {bottom} {c:g} IC={START/4:g}', f'R{j} p{j} {top} {r:g}']
    return '\n'.join(lines + [
        'Vsense pack load 0',
        f'Bload load 0 I={PLOAD:g}/({eta:g}*{PATH_EFF:g}*max(V(load),6))',
        '.tran 0.5m 4 0 0.5m UIC',
        '.meas TRAN t_hold_7v WHEN V(pack)=7 FALL=1',
        '.meas TRAN t_hold_8v WHEN V(pack)=8 FALL=1',
        '.meas TRAN pack_1p2s FIND V(pack) AT=1.2',
        '.end', '',
    ])


def exact_hold(caps, esrs, eta, v):
    p, inv_c = PLOAD/(eta*PATH_EFF), sum(1/c for c in caps)
    rp = sum(esrs)*p
    v0 = (START + math.sqrt(START**2-4*rp))/2
    # From V_oc = V_term + R*P/V_term, then integrate dt = V_term*dq/P.
    q = (START-v-rp/v)/inv_c
    assert min(START/4-q/c-p/v*r for c, r in zip(caps, esrs)) > CELL_MIN
    return (0.5*(v0*v0-v*v)-rp*math.log(v0/v))/(p*inv_c)


def interp(rows, t):
    for a, b in zip(rows, rows[1:]):
        if a[0] <= t <= b[0]:
            u = (t-a[0])/(b[0]-a[0])
            return [x+(y-x)*u for x, y in zip(a, b)]
    raise ValueError(f'Time {t} outside transient data')


def simulate(ngspice, output, original):
    with original.open(newline='') as f:
        baseline = {(r['case'], float(r['eta_boost'])): r for r in csv.DictReader(f)}
    curves, summaries = {}, []
    for case, (caps, esrs) in CASES.items():
        for eta in EFFICIENCIES:
            run = (output / 'runs' / f'{case.replace("%", "pct")}_{eta*100:.0f}').resolve()
            run.mkdir(parents=True, exist_ok=True)
            source = deck(case, caps, esrs, eta)
            (run/'hold.cir').write_text(source, encoding='ascii')
            control = '''.control
run
set wr_singlescale
set wr_vecnames
set numdgt=12
let cell1 = v(n1)
let cell2 = v(n2)-v(n1)
let cell3 = v(n3)-v(n2)
let cell4 = v(pack)-v(n3)
wrdata samples.txt v(pack) i(vsense) cell1 cell2 cell3 cell4
quit
.endc
'''
            (run/'batch.cir').write_text(source.removesuffix('.end\n')+control+'.end\n', encoding='ascii')
            subprocess.run([str(ngspice), '-b', '-o', 'ngspice.log', 'batch.cir'], cwd=run, capture_output=True, check=True)
            log = (run/'ngspice.log').read_text(encoding='ascii', errors='replace')
            if re.search(r'\berror\b|singular matrix|timestep too small|aborted|no convergence|stepping failed', log, re.I):
                raise RuntimeError(f'{run.name}: {log}')

            def meas(name):
                return float(re.search(rf'(?m)^{name}\s*=\s*([-+\d.eE]+)', log)[1])

            data = (run/'samples.txt').read_text(encoding='ascii').splitlines()
            rows = [tuple(map(float, line.split())) for line in data[1:] if line.strip()]
            assert len(rows) > 2000 and all(len(r) == 7 and all(map(math.isfinite, r)) for r in rows)
            t7, t8 = meas('t_hold_7v'), meas('t_hold_8v')
            task = interp(rows, 1.2)
            assert all(abs(t-exact_hold(caps, esrs, eta, v)) < .00002 for t, v in ((t7, 7.), (t8, 8.)))
            assert abs(task[1]-meas('pack_1p2s')) < .00002
            trace = [r for r in rows if r[0] < t7]+[interp(rows, t7)]
            assert min(min(r[3:]) for r in trace) > CELL_MIN
            curves[case, eta] = trace
            with (run/'waveform_to_7v.csv').open('w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['time_s','pack_terminal_V','input_A','cell1_terminal_V','cell2_terminal_V','cell3_terminal_V','cell4_terminal_V'])
                w.writerows(trace)
            ref = baseline[case, eta]
            summaries.append(dict(
                case=case, eta_boost=eta, hold_7v_s=t7, margin_7v_vs_1p2s_s=round(t7-1.2, 6), pass_7v_1p2s=t7>=1.2,
                hold_8v_s=t8, margin_8v_vs_1p2s_s=round(t8-1.2, 6), pass_8v_1p2s=t8>=1.2, pass_8v_1p0s=t8>=1.0,
                pack_at_1p2s_if_7v_cutoff_V=round(task[1], 6), min_cell_at_1p2s_if_7v_cutoff_V=round(min(task[3:]), 6),
                input_at_1p2s_if_7v_cutoff_A=round(task[2], 6), cycle_eta_7v_python_pct=round(float(ref['cycle_eta_pct']), 6),
                delta_hold_7v_vs_python_ms=round((t7-float(ref['hold_s']))*1000, 6),
            ))
    with (output/'summary.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0]))
        w.writeheader()
        w.writerows(summaries)
    return curves, summaries


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Reproduce DC V1.2 behavioral hold simulations')
    p.add_argument('--ngspice', type=Path, required=True)
    p.add_argument('--original-results', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    _, rows = simulate(args.ngspice.resolve(), args.out, args.original_results)
    for r in rows:
        print(f"{r['case']:18} {r['eta_boost']:.2f} 7V={r['hold_7v_s']:.5f}s 8V={r['hold_8v_s']:.5f}s V(1.2)={r['pack_at_1p2s_if_7v_cutoff_V']:.5f}V")
