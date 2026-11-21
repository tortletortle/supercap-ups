"""Audit preserved official TI archives; never changes the simulation model.
py -3 audit_models.py --repo PATH [--artifact-dir PATH]
"""
import argparse, csv, difflib, hashlib, json, re, subprocess, zipfile
from pathlib import Path

def sha(b): return hashlib.sha256(b).hexdigest()
def lf(b): return b.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
def csv_write(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def lines(b):
    result=[]
    for s in lf(b).decode('cp1252').splitlines():
        s=s.strip()
        if not s or s.startswith('*'): continue
        if s.startswith('+') and result: result[-1]+=' '+s[1:].strip()
        else: result.append(s)
    return [' '.join(s.upper().split()) for s in result]
def subckts(b):
    result={}; active=None; body=[]
    for s in lines(b):
        if s.startswith('.SUBCKT '): active=s.split()[1]; body=[s]
        elif active:
            body.append(s)
            if s.startswith('.ENDS'):
                result[active]={'declaration':body[0],'logical_lines':len(body),'sha256_logical':sha('\n'.join(body).encode())}
                active=None; body=[]
    return result
def header(b):
    fields=['Part','Date','Model Type','Simulator','Simulator Version','EVM Order Number','Datasheet','Model Version']
    result={}
    for field in fields:
        match=re.search(r'^\*\s*'+re.escape(field)+r':\s*(.+)$',lf(b).decode('cp1252'),re.M)
        result[field]=match.group(1).strip() if match else None
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--artifact-dir',type=Path,default=Path(__file__).resolve().parent); args=p.parse_args()
    root=args.artifact_dir.resolve()
    attempts=json.loads((root/'download_attempts.json').read_text(encoding='utf-8'))
    acquired={x['name']:x for x in attempts if x.get('status')==200}
    members={'slvmda9':'TPS61088_lib/TPS61088.lib','slvmau6a':'SLVMAU6/TPS61088_PSPICE_TRANS/TPS61088_TRANS.LIB'}
    archives={}; models={}; entries=[]
    for tag, member in members.items():
        data=(root/(tag+'.zip')).read_bytes(); meta=acquired[tag]
        assert sha(data)==meta['sha256']
        with zipfile.ZipFile(root/(tag+'.zip')) as z:
            assert z.testzip() is None
            for item in z.infolist():
                content=z.read(item) if not item.is_dir() else b''
                entries.append({'archive':tag+'.zip','path':item.filename,'is_directory':item.is_dir(),
                    'bytes':item.file_size,'compressed_bytes':item.compress_size,'crc32':f'{item.CRC:08x}',
                    'sha256':sha(content) if not item.is_dir() else '', 'zip_encrypted':bool(item.flag_bits&1)})
            b=z.read(member)
        models[tag]=b
        archives[tag]={**meta,'zip_integrity':'PASS','lib_path':member,'lib_bytes':len(b),'lib_sha256':sha(b),
            'lib_sha256_lf':sha(lf(b)),'header':header(b),
            'line_endings':{'crlf':b.count(b'\r\n'),'bare_lf':b.count(b'\n')-b.count(b'\r\n'),
                'bare_cr':b.count(b'\r')-b.count(b'\r\n')},'subcircuits':subckts(b),
            'encryption_markers':bool(re.search(rb'(?im)^\s*\.?(?:PROTECT|ENCRYPT)\b',b))}
    a=models['slvmda9']; b=models['slvmau6a']
    baseline=(args.repo/'sim/tps61088_v1_3/model/TPS61088_LT.LIB').read_bytes()
    patched=b; adaptations=[]
    for old,new in [(b'(2.35-6m)',b'2.344'),(b'(1.48+6m)',b'1.486')]:
        adaptations.append({'old':old.decode(),'new':new.decode(),'count':patched.count(old)})
        patched=patched.replace(old,new)
    sa=subckts(a); sb=subckts(b); rows=[]
    for name in sorted(sa.keys()|sb.keys()):
        left=sa.get(name,{}); right=sb.get(name,{})
        rows.append({'subcircuit':name,'slvmda9_declaration':left.get('declaration',''),
            'slvmau6a_declaration':right.get('declaration',''),'slvmda9_logical_sha256':left.get('sha256_logical',''),
            'slvmau6a_logical_sha256':right.get('sha256_logical',''),'equal':left==right})
    comparison={'audit_scope':'ordinary TPS61088; no TPS61088-Q1 download used',
        'repository_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.repo,text=True).strip(),
        'archives':archives,'binary_equal':a==b,'equal_after_crlf_to_lf':a.replace(b'\r\n',b'\n')==b,
        'logical_spice_equal':lines(a)==lines(b),'subcircuits_equal':sa==sb,'subcircuit_count':len(sa),
        'baseline':{'path':'sim/tps61088_v1_3/model/TPS61088_LT.LIB','bytes':len(baseline),'sha256':sha(baseline),
            'adaptations':adaptations,'patched_slvmau6a_equals_repository':patched==baseline},
        'product_page_refresh':'failed; HTTP 404 recorded in download_attempts.json',
        'interpretation':'Different ZIP packaging and line endings; identical model content after CRLF normalization. Package Rev.A does not imply an internal model version change. No simulator cross-validation performed by this audit.'}
    csv_write(root/'zip_inventory.csv',entries); csv_write(root/'subcircuit_comparison.csv',rows)
    rows=[{'archive':tag,'zip_bytes':v['bytes'],'zip_sha256':v['sha256'],'lib_path':v['lib_path'],
        'lib_bytes':v['lib_bytes'],'lib_sha256':v['lib_sha256'],**v['header']} for tag,v in archives.items()]
    csv_write(root/'model_versions.csv',rows)
    (root/'model_comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    diff=''.join(difflib.unified_diff(lf(a).decode('cp1252').splitlines(True),lf(b).decode('cp1252').splitlines(True),
        fromfile='SLVMDA9-after-LF',tofile='SLVMAU6A-after-LF'))
    (root/'official_models_lf.diff').write_text(diff,encoding='utf-8')
    diff=''.join(difflib.unified_diff(b.decode('cp1252').splitlines(True),baseline.decode('cp1252').splitlines(True),
        fromfile='SLVMAU6A-original',tofile='TPS61088_LT.LIB'))
    (root/'official_to_repository.diff').write_text(diff,encoding='utf-8')
    assert comparison['equal_after_crlf_to_lf'] and comparison['subcircuits_equal']
    assert comparison['baseline']['patched_slvmau6a_equals_repository']
    print(json.dumps({'official_models_equal_after_crlf_to_lf':True,'subcircuits':len(sa),
        'repository_reproduced_with_only_two_adaptations':True,'artifacts':str(root)},ensure_ascii=False))
if __name__=='__main__': main()
