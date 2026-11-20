"""Quasistatic, constant-power four-cell model. Pure Python; not IC/SPICE validation."""
import csv, math, pathlib
OUT=pathlib.Path(__file__).resolve().parent
PLOAD=12.; VFULL=9.4; VMIN=7.; CELL_MIN=1.0; IC=0.5
ETA_BUCK=.95; ETA_BOOST=.92; ETA_PATH=.99
DT=.0005; TASK=1.2
CASES=[('nominal', [10.]*4,[.075]*4),('tol_-10%', [9.]*4,[.075]*4),('stress_EO L'.replace(' ',''),[6.3]*4,[.1125]*4),('single_weak_cell',[6.3,9.,9.,9.],[.1125,.075,.075,.075])]
def run(name,c,r,eta,dt=DT):
    v0=[VFULL/4]*4; v=v0[:]; R=sum(r); t=q=ed=0.; vmin=1e9; peak=0.; cellmin=1e9; snap=None; rows=[]
    p=PLOAD/(eta*ETA_PATH)
    while t<10:
        voc=sum(v); disc=voc*voc-4*R*p
        if disc<=0: break
        i=2*p/(voc+math.sqrt(disc)); vt=voc-R*i; cell=min(x-i*y for x,y in zip(v,r))
        if vt<VMIN or cell<CELL_MIN:break
        h=min(dt, TASK-t) if t<TASK else dt
        if h<1e-12: h=dt
        q+=i*h; ed+=R*i*i*h; t+=h
        v=[x-i*h/y for x,y in zip(v,c)]; peak=max(peak,i); vmin=min(vmin,vt); cellmin=min(cellmin,cell)
        if len(rows)==0 or t-rows[-1][0]>=.01: rows.append((t,sum(v),vt,i,cell))
        if snap is None and t>=TASK-1e-10: snap=(t,q,v[:],ed,vmin,cellmin,peak)
    if snap is None:snap=(t,q,v[:],ed,vmin,cellmin,peak)
    ts,qs,vs,ews,vts,vcs,ips=snap
    # Integrate recharge ESR loss over charge coordinate; CC/CV taper to initial OCV.
    # Energy only; auxiliary power, leakage and finite termination not included.
    ec_loss=0.; n=2000
    if qs>0:
        dq=qs/n
        for k in range(n):
            x=(k+.5)*dq; u=sum(a+x/b for a,b in zip(vs,c)); ic=max(0.,min(IC,(VFULL-u)/R)); ec_loss+=R*ic*dq
    delta=sum(0.5*a*(b*b-d*d) for a,b,d in zip(c,v0,vs))
    ein=(delta+ec_loss)/ETA_BUCK; eout=PLOAD*ts
    return dict(case=name,eta_boost=eta,hold_s=t,task_pass=t>=TASK,task_energy_J=eout,cycle_eta_pct=100*eout/ein if ein else 0,discharge_eta_pct=100*eout/delta if delta else 0,task_min_pack_term_V=vts,task_min_cell_term_V=vcs,task_peak_A=ips,task_esr_discharge_J=ews,task_esr_charge_J=ec_loss,energy_error_J=delta-(p*ts+ews)),rows
results=[]
for name,c,r in CASES:
    for eta in [.90,.92,.95]:
        result,rows=run(name,c,r,eta);results.append(result)
        if eta==ETA_BOOST:
            with (OUT/f'trace_{name}.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['time_s','pack_ocv_V','pack_terminal_V','input_A','min_cell_terminal_V']);w.writerows(rows)
with (OUT/'results.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=results[0].keys());w.writeheader();w.writerows(results)
for a in results:
    if a['eta_boost']==ETA_BOOST:print(a['case'],round(a['hold_s'],3),round(a['cycle_eta_pct'],2),round(a['task_min_pack_term_V'],3),round(a['energy_error_J'],5))
# convergence check, same model with half timestep
for name,c,r in CASES:
    a,_=run(name,c,r,ETA_BOOST); b,_=run(name,c,r,ETA_BOOST,DT/2)
    print('dt check',name,round(abs(a['hold_s']-b['hold_s']),5),round(abs(a['cycle_eta_pct']-b['cycle_eta_pct']),5))
