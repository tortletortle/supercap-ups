"""Export evidence from the first V1.4 run; never starts or edits a simulation.

Usage: py -3 sim/tps61088_v1_4/scripts/analyze_first_case.py --raw <local .raw>
Requires numpy and matplotlib. Raw measurements remain authoritative in the
unmodified LTspice log. CSV time windows below retain every stored sample.
"""
import argparse
import csv
import gzip
import json
from pathlib import Path
import re

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def load_raw(path):
    with path.open('rb') as f:
        header_bytes = f.read(65536)
    offset = None
    for ending in ('Binary:\n', 'Binary:\r\n'):
        marker = ending.encode('utf-16le')
        found = header_bytes.find(marker)
        if found >= 0:
            offset = found + len(marker)
            break
    if offset is None:
        raise ValueError('No LTspice UTF-16 Binary marker')
    header = header_bytes[:offset].decode('utf-16le')
    nvars = int(re.search(r'No\. Variables:\s+(\d+)', header).group(1))
    npoints = int(re.search(r'No\. Points:\s+(\d+)', header).group(1))
    names = re.findall(r'^\s*\d+\s+([^\t\r\n]+)\t', header, re.M)
    flags = re.search(r'Flags:\s+([^\r\n]+)', header).group(1)
    if 'double' not in flags or 'fastaccess' in flags:
        raise ValueError('This exporter requires interleaved double real RAW')
    expected = offset + 8 * nvars * npoints
    if path.stat().st_size != expected or len(names) != nvars:
        raise ValueError(f'Incomplete or unsupported RAW: {path.stat().st_size} != {expected}')
    a = np.memmap(path, mode='r', dtype='<f8', offset=offset, shape=(npoints, nvars))
    return header, names, a


def rising_times(t, y, level):
    i = np.flatnonzero((y[:-1] < level) & (y[1:] >= level))
    return t[i] + (level-y[i])/(y[i+1]-y[i])*(t[i+1]-t[i])


def write_rows(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def write_wave(path, names, values):
    with gzip.open(path, 'wt', newline='', encoding='utf-8') as f:
        np.savetxt(f, values, delimiter=',', header=','.join(names), comments='', fmt='%.12g')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--results', type=Path, default=Path(__file__).resolve().parents[1]/'results/first_case')
    args = p.parse_args()
    root = args.results.resolve()
    log = (root/'ltspice_original.log').read_text(encoding='utf-8-sig', errors='replace')
    measures = {}
    required = ('t90','t98','sw_t6001','sw_t6101','f_sw_khz','avg_vout',
                'ripple','peak_i','peak_start','iin_avg','iout_avg','pin_avg','pout_avg','eta_pct')
    for name in required:
        line = next((s for s in log.splitlines() if s.startswith(name+':')), '')
        pattern = r' AT\s+([-+\d.eE]+)(?:\s|$)' if ' AT ' in line else r'=\s*([-+\d.eE]+)(?:\s|$)'
        m = re.search(pattern, line)
        if not m:
            raise ValueError(f'Missing/failed LTspice measurement {name}; do not move measurement indices')
        measures[name] = float(m.group(1))
    header, names, a = load_raw(args.raw)
    idx = {n.lower(): i for i,n in enumerate(names)}
    t = a[:,idx['time']]
    sw = a[:,idx['v(sw)']]
    out = a[:,idx['v(vout)']]
    il = a[:,idx['i(l1)']]
    vin = a[:,idx['v(vin)']]
    load = a[:,idx['i(vload)']]
    ss = a[:,idx['v(ss)']]
    if not np.all(np.isfinite(a)) or not np.all(np.diff(t) >= 0):
        raise ValueError('Nonfinite vectors or decreasing time')
    rises = rising_times(t, sw, 10.)
    if len(rises) < 6101:
        raise ValueError(f'Only {len(rises)} rising edges at 10 V; prescribed measurement invalid')
    t0, t1 = measures['sw_t6001'], measures['sw_t6101']
    seq = measures['t98'] < t0 < t1 < .026
    theoretical = 1/(324e3*23e-12/4+89e-9*12/7)/1e3
    rows = []
    units = dict(t90='s',t98='s',sw_t6001='s',sw_t6101='s',f_sw_khz='kHz',
                 avg_vout='V',ripple='Vpp',peak_i='A',peak_start='A',iin_avg='A',
                 iout_avg='A',pin_avg='W',pout_avg='W',eta_pct='%')
    for k in required:
        window = '24–26 ms' if k in required[5:8]+required[9:13] or k=='eta_pct' else '0–26 ms'
        rows.append(dict(measurement=k,value=f'{measures[k]:.12g}',unit=units[k],
                         definition=window,source='ltspice_original.log'))
    rows += [dict(measurement='theoretical_f_sw_khz',value=f'{theoretical:.12g}',unit='kHz',
                  definition='TI equation, VIN=7 V VOUT=12 V RFSW=324 kohm',source='calculation'),
             dict(measurement='frequency_error_pct',value=f'{100*(measures["f_sw_khz"]/theoretical-1):.12g}',unit='%',
                  definition='100*(measured/theoretical-1)',source='derived')]
    write_rows(root/'measurements.csv', rows)
    # Independent extraction uses every RAW sample and the original 10 V threshold.
    periods = np.diff(rises[6000:6101])
    edge_rows = [dict(rise_index=i+1,time_s=f'{rises[i]:.15g}') for i in range(6000,6101)]
    write_rows(root/'frequency_edges.csv',edge_rows)
    threshold_rows = []
    for level in (2., 5., 8., 9., 10., 11.):
        r = rising_times(t,sw,level)
        late = r[(r >= .024)&(r <= .026)]
        threshold_rows.append(dict(threshold_V=level,steady_rising_edges=len(late),
            steady_f_kHz=(len(late)-1)/(late[-1]-late[0])/1e3 if len(late)>1 else '',
            minimum_period_us=float(np.min(np.diff(late))*1e6) if len(late)>1 else ''))
    write_rows(root/'threshold_crosscheck.csv', threshold_rows)
    # Count 10 V rises only after SW has returned below 2 V: ringing would otherwise
    # produce repeated 10 V crossings in a single physical high pulse.
    transitions = np.flatnonzero(((sw[:-1] >= 2)&(sw[1:] < 2)) |
                                  ((sw[:-1] < 10)&(sw[1:] >= 10)))
    armed = bool(sw[0] < 2)
    accepted = []
    rejected = []
    for i in transitions:
        if sw[i+1] < 2:
            armed = True
        else:
            tr = t[i]+(10-sw[i])/(sw[i+1]-sw[i])*(t[i+1]-t[i])
            (accepted if armed else rejected).append(float(tr))
            armed = False
    late_rejected = [x for x in rejected if t0 <= x <= t1 or .024 <= x <= .026]
    ss_time = rising_times(t, ss, 1.204)
    pin_wave = -vin*a[:,idx['i(v1)']]
    pout_wave = out*load
    mask = (t >= .024)&(t <= .026)
    st = t[mask]
    def avg(v):
        return float(np.trapezoid(v[mask], st)/(st[-1]-st[0]))
    check = dict(raw_point_count=len(t),raw_variables=names,raw_last_time_s=float(t[-1]),
        t98_before_both_frequency_edges=bool(seq),
        raw_rise6001_s=float(rises[6000]),raw_rise6101_s=float(rises[6100]),
        raw_100period_frequency_kHz=float(100/(rises[6100]-rises[6000])/1e3),
        raw_vs_log_edge_max_error_s=float(max(abs(rises[6000]-t0),abs(rises[6100]-t1))),
        frequency_window_min_period_us=float(periods.min()*1e6),
        frequency_window_max_period_us=float(periods.max()*1e6),
        frequency_window_period_mean_us=float(periods.mean()*1e6),
        frequency_window_period_std_us=float(periods.std()*1e6),
        rejected_10V_rises_without_2V_reset_in_measured_windows=late_rejected,
        ss_1p204V_first_crossing_s=float(ss_time[0]) if len(ss_time) else None,
        raw_steady_vout_min_V=float(out[mask].min()),raw_steady_vout_max_V=float(out[mask].max()),
        raw_steady_vout_avg_V=avg(out),raw_steady_ripple_V=float(np.ptp(out[mask])),
        raw_steady_iout_avg_A=avg(load),raw_steady_ILpeak_A=float(il[mask].max()),
        raw_full_ILpeak_A=float(il.max()),raw_IL_peak_time_s=float(t[il.argmax()]),
        raw_steady_pin_W=avg(pin_wave),raw_steady_pout_W=avg(pout_wave),
        raw_steady_eta_pct=100*avg(pout_wave)/avg(pin_wave),
        theoretical_f_sw_kHz=theoretical,
        frequency_error_pct=100*(measures['f_sw_khz']/theoretical-1),
        note='RAW interpolation/integration cross-check; LTspice original log remains measurement source')
    (root/'waveform_checks.json').write_text(json.dumps(check,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (root/'raw_header.txt').write_text(header,encoding='utf-8')
    wave_names=['time_s','V_sw_V','V_out_V','I_L1_A','V_in_V','I_load_A','V_ss_V']
    columns=[idx['time'],idx['v(sw)'],idx['v(vout)'],idx['i(l1)'],idx['v(vin)'],idx['i(vload)'],idx['v(ss)']]
    for name,begin,end in [('frequency_window',t0-2e-6,t1+2e-6),('steady_window',.024,.026),
                            ('startup_peak_window',check['raw_IL_peak_time_s']-10e-6,check['raw_IL_peak_time_s']+10e-6)]:
        k=(t >= begin)&(t <= end)
        write_wave(root/(name+'.csv.gz'),wave_names,np.asarray(a[k][:,columns]))
    # Min/max bins preserve extrema for startup overview, unlike a single uniform stride.
    borders=np.linspace(0,len(t),4001,dtype=int)
    overview=[]
    for begin,end in zip(borders[:-1],borders[1:]):
        if end <= begin: continue
        overview.append([t[begin],t[end-1],out[begin:end].min(),out[begin:end].max(),
                         il[begin:end].min(),il[begin:end].max(),sw[begin:end].min(),sw[begin:end].max()])
    env=np.array(overview)
    np.savetxt(root/'startup_envelope.csv',env,delimiter=',',comments='',fmt='%.12g',
        header='time_start_s,time_end_s,V_out_min_V,V_out_max_V,I_L1_min_A,I_L1_max_A,V_sw_min_V,V_sw_max_V')
    fig,axs=plt.subplots(3,1,figsize=(11,8),sharex=True)
    for ax,lo,hi,label in zip(axs,(2,4,6),(3,5,7),('V(out) [V]','I(L1) [A]','V(sw) [V]')):
        ax.fill_between(env[:,0]*1e3,env[:,lo],env[:,hi],alpha=.7,linewidth=.3)
        ax.set_ylabel(label); ax.grid(alpha=.25)
        ax.axvline(measures['t98']*1e3,color='tab:red',ls='--',lw=.8,label='t98')
    axs[0].legend(); axs[-1].set_xlabel('Time [ms]')
    fig.suptitle('V1.4 first case: original 7 V / 324 kohm deck (min/max overview)')
    fig.tight_layout(); fig.savefig(root/'startup_overview.png',dpi=160); plt.close(fig)
    fig,axs=plt.subplots(3,1,figsize=(11,8))
    windows=[(t0-2e-6,t1+2e-6),(t0,t0+12e-6),(.02598,.026)]
    for ax,(begin,end) in zip(axs,windows):
        k=(t>=begin)&(t<=end)
        ax.plot(t[k]*1e3,sw[k],lw=.7); ax.axhline(10,color='tab:red',ls='--',lw=.6)
        ax.set_ylabel('V(sw) [V]'); ax.set_xlabel('Time [ms]'); ax.grid(alpha=.25)
    for tt in (t0,t1): axs[0].axvline(tt*1e3,color='tab:orange',ls='--')
    axs[0].set_title('Original RISE=6001 to RISE=6101 interval')
    axs[1].set_title('Detail at RISE=6001; every stored sample')
    axs[2].set_title('Final steady-state detail; every stored sample')
    fig.tight_layout(); fig.savefig(root/'switching_frequency.png',dpi=160); plt.close(fig)
    fig,axs=plt.subplots(3,1,figsize=(11,8))
    axs[0].plot(st*1e3,out[mask],lw=.45);axs[0].set_ylabel('V(out) [V]')
    k=(t>=.02598)&(t<=.026)
    axs[1].plot(t[k]*1e3,(out[k]-measures['avg_vout'])*1e3,lw=.7);axs[1].set_ylabel('Output ripple [mV]')
    axs[2].plot(t[k]*1e3,il[k],lw=.7);axs[2].set_ylabel('I(L1) [A]')
    for ax in axs:ax.grid(alpha=.25);ax.set_xlabel('Time [ms]')
    fig.suptitle('V1.4 first case: output regulation and inductor current')
    fig.tight_layout();fig.savefig(root/'output_and_inductor.png',dpi=160);plt.close(fig)
    print(json.dumps({'measurements':measures,'checks':check},indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
