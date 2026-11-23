"""Analyze retained V1.4 RAW files without running or changing any circuit.

The prescribed RISE=6001/6101 measurements are never replaced. A separate
24-26 ms extraction is explicitly supplemental when either edge is missing.
Requires numpy/matplotlib, and the first-round RAW for the four-case figures.
"""
import argparse
import csv
import json
from pathlib import Path
import re

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from analyze_first_case import load_raw, rising_times, write_rows, write_wave


CASES = [('freq_vin7_rfsw324k', 7., 324e3),
         ('freq_vin7_rfsw510k', 7., 510e3),
         ('freq_vin9p4_rfsw324k', 9.4, 324e3),
         ('freq_vin9p4_rfsw517k', 9.4, 517e3)]
PROBE = 'freq_vin7_rfsw324k_fsw_probe'
CORE = ('t90', 't98', 'sw_t6001', 'sw_t6101', 'f_sw_khz', 'avg_vout',
        'ripple', 'peak_i', 'peak_start')
POWER = ('iin_avg', 'iout_avg', 'pin_avg', 'pout_avg', 'eta_pct')
PROBES = ('avg_vsw', 'avg_vfsw', 'min_vfsw', 'max_vfsw',
          'avg_rfsw_current', 'pp_rfsw_current')
UNITS = dict(t90='s', t98='s', sw_t6001='s', sw_t6101='s', f_sw_khz='kHz',
             avg_vout='V', ripple='Vpp', peak_i='A', peak_start='A',
             iin_avg='A', iout_avg='A', pin_avg='W', pout_avg='W', eta_pct='%',
             avg_vsw='V', avg_vfsw='V', min_vfsw='V', max_vfsw='V',
             avg_rfsw_current='A', pp_rfsw_current='App')


def parse_measures(log, required):
    measures, rows = {}, []
    for name in required:
        line = next((s for s in log.splitlines() if s.startswith(name+':')), '')
        pattern = r' AT\s+([-+\d.eE]+)(?:\s|$)' if ' AT ' in line else r'=\s*([-+\d.eE]+)(?:\s|$)'
        match = re.search(pattern, line)
        value = float(match.group(1)) if match else None
        measures[name] = value
        fail = next((s for s in log.splitlines()
                     if re.search(r'Measurement\s+["\x27]?'+re.escape(name)+r'["\x27]?\s+FAIL', s, re.I)), '')
        rows.append(dict(measurement=name, value=value if value is not None else '',
                         unit=UNITS[name], status='measured' if match else 'FAILED_or_missing',
                         window='0-26 ms' if name in CORE[:5]+('peak_start',) else '24-26 ms',
                         source='ltspice_original.log', original_line=line or fail))
    return measures, rows


def time_average(t, values, begin=.024, end=.026):
    mask = (t > begin) & (t < end)
    tt = np.concatenate(([begin], t[mask], [end]))
    vv = np.concatenate(([np.interp(begin, t, values)], values[mask], [np.interp(end, t, values)]))
    return float(np.trapezoid(vv, tt)/(end-begin))


def analyze_case(raw, root, vin, rfsw, probe=False, historical=False):
    log = (root/'ltspice_original.log').read_text(encoding='utf-8-sig', errors='replace')
    measures, rows = parse_measures(log, CORE+(PROBES if probe else POWER))
    header, names, a = load_raw(raw)
    idx = {name.lower(): n for n, name in enumerate(names)}
    t, sw, out, il = (a[:,idx[n]] for n in ('time','v(sw)','v(vout)','i(l1)'))
    load = a[:,idx['i(vload)']]
    if not np.isfinite(a).all() or not np.all(np.diff(t) >= 0):
        raise ValueError('Nonfinite vectors or decreasing time: '+str(raw))
    rises = rising_times(t, sw, 10.)
    late = rises[(rises >= .024)&(rises <= .026)]
    theory = 1/(rfsw*23e-12/4+89e-9*12/vin)/1e3
    fixed = measures['f_sw_khz']
    seq = bool(all(measures[n] is not None for n in ('t98','sw_t6001','sw_t6101'))
               and measures['t98'] < measures['sw_t6001'] < measures['sw_t6101'] < .026)
    supplemental = float((len(late)-1)/(late[-1]-late[0])/1e3) if len(late)>1 else None
    k = (t >= .024)&(t <= .026)
    transitions = np.flatnonzero(((sw[:-1] >= 2)&(sw[1:] < 2)) |
                                ((sw[:-1] < 10)&(sw[1:] >= 10)))
    armed = bool(sw[0] < 2)
    rejected = []
    for i in transitions:
        if sw[i+1] < 2:
            armed = True
        else:
            tr = t[i]+(10-sw[i])/(sw[i+1]-sw[i])*(t[i+1]-t[i])
            if not armed:
                rejected.append(float(tr))
            armed = False
    measured_lo, measured_hi = measures['sw_t6001'], measures['sw_t6101']
    rejects_late = [x for x in rejected if .024 <= x <= .026]
    rejects_fixed = [x for x in rejected if measured_lo is not None and measured_hi is not None
                     and measured_lo <= x <= measured_hi]
    rc_edge0 = float(rises[6000]) if len(rises)>6000 else None
    rc_edge1 = float(rises[6100]) if len(rises)>6100 else None
    raw_fixed = 100/(rc_edge1-rc_edge0)/1e3 if rc_edge0 is not None and rc_edge1 is not None else None
    raw_edge_error = max(abs(rc_edge0-measured_lo), abs(rc_edge1-measured_hi)) if seq else None
    environment = json.loads((root/'environment.json').read_text(encoding='utf-8'))
    solver_ok = (environment.get('exit_code') == 0
                 and 'solver = Normal' in log and 'method = Gear' in log
                 and 'Total elapsed time:' in log and abs(float(t[-1])-.026)<1e-12
                 and not re.search(r'Time step too small|singular matrix|Fatal Error', log, re.I))
    ss = a[:,idx['v(ss)']]
    ss_end = rising_times(t, ss, 1.204)
    check = dict(raw_point_count=len(t), raw_variables=names, raw_last_time_s=float(t[-1]),
        solver_normal_gear_completed=bool(solver_ok), process_exit_code=environment.get('exit_code'),
        diode_small_N_warning_count=log.count('Emission coefficient, N=0.0001'),
        raw_10V_rise_count=len(rises), prescribed_timing_valid=seq,
        raw_rise6001_s=rc_edge0, raw_rise6101_s=rc_edge1,
        raw_100period_frequency_kHz=raw_fixed, raw_vs_log_edge_max_error_s=raw_edge_error,
        supplemental_24_26ms_frequency_kHz=supplemental,
        supplemental_frequency_error_pct=100*(supplemental/theory-1) if supplemental else None,
        supplemental_24_26ms_edge_count=len(late),
        supplemental_min_period_us=float(np.diff(late).min()*1e6) if len(late)>1 else None,
        supplemental_max_period_us=float(np.diff(late).max()*1e6) if len(late)>1 else None,
        supplemental_period_std_us=float(np.diff(late).std()*1e6) if len(late)>1 else None,
        rejected_10V_rises_without_2V_reset_24_26ms=rejects_late,
        rejected_10V_rises_without_2V_reset_fixed_window=rejects_fixed,
        ss_1p204V_first_crossing_s=float(ss_end[0]) if len(ss_end) else None,
        raw_steady_vout_avg_V=time_average(t,out), raw_steady_vout_min_V=float(out[k].min()),
        raw_steady_vout_max_V=float(out[k].max()), raw_steady_ripple_V=float(np.ptp(out[k])),
        raw_steady_iout_avg_A=time_average(t,load), raw_steady_ILpeak_A=float(il[k].max()),
        raw_full_ILpeak_A=float(il.max()), raw_ILpeak_time_s=float(t[il.argmax()]),
        theoretical_frequency_kHz=theory,
        prescribed_frequency_error_pct=100*(fixed/theory-1) if fixed is not None else None,
        note='Supplemental window is independent evidence, never a replacement for failed fixed-index measurements.')
    # Efficiency from external vectors is a macro-model calculation only.
    pin = -a[:,idx['v(vin)']]*a[:,idx['i(v1)']]
    pout = out*load
    check['raw_steady_pin_W'] = time_average(t,pin)
    check['raw_steady_pout_W'] = time_average(t,pout)
    check['raw_model_efficiency_pct'] = 100*check['raw_steady_pout_W']/check['raw_steady_pin_W']
    if probe:
        fsw = a[:,idx['v(fsw)']]
        ir = a[:,idx['i(rfsw)']]
        check['raw_avg_vfsw_V'] = time_average(t,fsw)
        check['raw_min_vfsw_V'] = float(fsw[k].min())
        check['raw_max_vfsw_V'] = float(fsw[k].max())
        check['raw_avg_irfsw_A'] = time_average(t,ir)
        check['raw_rfsw_ohms_law_max_abs_error_A'] = float(np.max(np.abs(ir[k]-(fsw[k]-sw[k])/rfsw)))
        high = k & (sw > 11.5) & (ir < -10e-6)
        ratios = sw[high]/(-ir[high])
        check['high_phase_vsw_over_inward_irfsw_min_ohm'] = float(ratios.min())
        check['high_phase_vsw_over_inward_irfsw_max_ohm'] = float(ratios.max())
        check['high_phase_ratio_criterion'] = '24-26 ms; VSW>11.5 V and IRFSW<-10 uA; range only, not a cycle average'
    if not historical:
        write_rows(root/'measurements.csv', rows)
        (root/'waveform_checks.json').write_text(json.dumps(check,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        (root/'raw_header.txt').write_text(header,encoding='utf-8')
        write_rows(root/'all_10V_rising_edges.csv', [dict(rise_index=i+1,time_s=f'{v:.15g}') for i,v in enumerate(rises)])
        thresholds = []
        for level in (2.,5.,8.,9.,10.,11.):
            rr = rising_times(t,sw,level)
            rr = rr[(rr>=.024)&(rr<=.026)]
            thresholds.append(dict(threshold_V=level, steady_rising_edges=len(rr),
                supplemental_steady_f_kHz=(len(rr)-1)/(rr[-1]-rr[0])/1e3 if len(rr)>1 else '',
                minimum_period_us=float(np.diff(rr).min()*1e6) if len(rr)>1 else ''))
        write_rows(root/'threshold_crosscheck.csv',thresholds)
        columns = [idx[x] for x in ('time','v(sw)','v(vout)','i(l1)','v(vin)','i(vload)','v(ss)')]
        col_names = ['time_s','V_sw_V','V_out_V','I_L1_A','V_in_V','I_load_A','V_ss_V']
        if probe:
            columns += [idx['v(fsw)'],idx['i(rfsw)']]
            col_names += ['V_fsw_V','I_RFSW_A']
        for title, begin, end in [('steady_window',.024,.026),('switching_detail',.02598,.026)]:
            kk = (t>=begin)&(t<=end)
            write_wave(root/(title+'.csv.gz'),col_names,np.asarray(a[kk][:,columns]))
    # Min/max envelope avoids aliasing in a long startup plot.
    overview = []
    borders = np.linspace(0,len(t),4001,dtype=int)
    for begin,end in zip(borders[:-1],borders[1:]):
        if end>begin:
            overview.append([t[begin],t[end-1],out[begin:end].min(),out[begin:end].max(),
                             il[begin:end].min(),il[begin:end].max()])
    env = np.asarray(overview)
    if not historical:
        np.savetxt(root/'startup_envelope.csv',env,delimiter=',',comments='',fmt='%.12g',
                   header='time_start_s,time_end_s,V_out_min_V,V_out_max_V,I_L1_min_A,I_L1_max_A')
    print(json.dumps(dict(case=root.name, measurements=measures, checks=check),ensure_ascii=False),flush=True)
    return dict(root=root, raw=raw, measures=measures, check=check, t=t, sw=sw, out=out, il=il,
                env=env, a=a, idx=idx, vin=vin, rfsw=rfsw, theory=theory)


def compare_figures(data, root):
    labels = [f'{d["vin"]:g} V / {d["rfsw"]/1e3:g} kohm' for d in data]
    fig, ax = plt.subplots(figsize=(10,5))
    x = np.arange(4)
    ax.bar(x-.2,[d['theory'] for d in data],width=.4,label='TI equation')
    fixed = [d['measures']['f_sw_khz'] or np.nan for d in data]
    ax.bar(x+.2,fixed,width=.4,label='Prescribed RISE 6001/6101')
    supplemental = [d['check']['supplemental_24_26ms_frequency_kHz'] for d in data]
    ax.scatter(x+.2,supplemental,c='tab:red',marker='x',s=55,label='Supplemental 24-26 ms edges')
    for i,d in enumerate(data):
        if fixed[i]!=fixed[i]:
            ax.text(i,supplemental[i]+18,'Fixed-index FAILED',ha='center',fontsize=8)
    ax.set_xticks(x,labels);ax.set_ylabel('Switching frequency [kHz]');ax.grid(axis='y',alpha=.25)
    ax.legend();ax.set_title('Four original frequency cases: prescribed and supplemental evidence')
    fig.tight_layout();fig.savefig(root/'four_case_frequency.png',dpi=170);plt.close(fig)
    fig, axs = plt.subplots(2,2,figsize=(12,8),sharex=True,sharey=True)
    for ax,d,label in zip(axs.ravel(),data,labels):
        env=d['env'];ax.fill_between(env[:,0]*1e3,env[:,2],env[:,3],alpha=.7,lw=.3)
        if d['measures']['t98'] is not None:ax.axvline(d['measures']['t98']*1e3,c='r',ls='--',lw=.7,label='t98')
        ax.set_title(label);ax.set_xlabel('Time [ms]');ax.set_ylabel('V(out) [V]');ax.grid(alpha=.25);ax.legend()
    fig.suptitle('Startup overview: min/max envelopes of all RAW samples')
    fig.tight_layout();fig.savefig(root/'four_case_startup.png',dpi=170);plt.close(fig)
    fig, axs = plt.subplots(4,1,figsize=(12,10),sharex=True)
    for ax,d,label in zip(axs,data,labels):
        k=(d['t']>=.02598)&(d['t']<=.026)
        ax.plot((d['t'][k]-.02598)*1e6,d['sw'][k],lw=.7)
        ax.axhline(10,c='tab:red',ls='--',lw=.5)
        ax.set_title(label);ax.set_ylabel('V(sw) [V]');ax.grid(alpha=.25)
    axs[-1].set_xlabel('Time from 25.980 ms [us]')
    fig.suptitle('Four-case SW detail: every stored sample; original 10 V threshold')
    fig.tight_layout();fig.savefig(root/'four_case_switching.png',dpi=170);plt.close(fig)
    fig, axs = plt.subplots(4,2,figsize=(12,10),sharex=True)
    for row,d,label in zip(axs,data,labels):
        k=(d['t']>=.02598)&(d['t']<=.026);tt=(d['t'][k]-.02598)*1e6
        row[0].plot(tt,(d['out'][k]-d['measures']['avg_vout'])*1e3,lw=.7)
        row[1].plot(tt,d['il'][k],lw=.7)
        row[0].set_ylabel('Ripple [mV]');row[1].set_ylabel('I(L1) [A]')
        for ax in row:ax.grid(alpha=.25);ax.set_title(label)
    for ax in axs[-1]:ax.set_xlabel('Time from 25.980 ms [us]')
    fig.suptitle('Output and inductor detail; ripple is centered on each 24-26 ms mean')
    fig.tight_layout();fig.savefig(root/'four_case_output_current.png',dpi=170);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-root',required=True,type=Path)
    p.add_argument('--first-raw',required=True,type=Path)
    p.add_argument('--results',type=Path,default=Path(__file__).resolve().parents[1]/'results/frequency_round2')
    args=p.parse_args();v14=Path(__file__).resolve().parents[1]
    data=[];summary=[]
    for i,(name,vin,rfsw) in enumerate(CASES):
        raw=args.first_raw if i==0 else args.native_root/name/(name+'.raw')
        root=v14/'results/first_case' if i==0 else args.results/name
        d=analyze_case(raw,root,vin,rfsw,historical=i==0);data.append(d)
        m,c=d['measures'],d['check']
        summary.append(dict(case=name,vin_V=vin,rfsw_ohm=rfsw,theory_kHz=d['theory'],
            prescribed_f_kHz=m['f_sw_khz'] if m['f_sw_khz'] is not None else '',
            prescribed_error_pct=c['prescribed_frequency_error_pct'] if c['prescribed_frequency_error_pct'] is not None else '',
            prescribed_timing_valid=c['prescribed_timing_valid'],raw_10V_rise_count=c['raw_10V_rise_count'],
            t98_s=m['t98'],sw_t6001_s=m['sw_t6001'] if m['sw_t6001'] is not None else '',
            sw_t6101_s=m['sw_t6101'] if m['sw_t6101'] is not None else '',
            supplemental_24_26ms_kHz=c['supplemental_24_26ms_frequency_kHz'],
            supplemental_error_pct=c['supplemental_frequency_error_pct'],
            avg_vout_V=m['avg_vout'],iout_avg_A=m['iout_avg'],ripple_mVpp=m['ripple']*1e3,
            steady_ILpeak_A=m['peak_i'],full_ILpeak_A=m['peak_start'],
            macro_model_eta_pct=m['eta_pct'],solver_completed=c['solver_normal_gear_completed'],
            source_log=str(root.relative_to(v14)/'ltspice_original.log')))
    write_rows(args.results/'frequency_comparison.csv',summary)
    compare_figures(data,args.results)
    analyze_case(args.native_root/PROBE/(PROBE+'.raw'),args.results/PROBE,7.,324e3,probe=True)


if __name__=='__main__':
    main()
