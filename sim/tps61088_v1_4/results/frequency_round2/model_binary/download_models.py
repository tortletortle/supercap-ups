"""Reacquire ordinary TPS61088 resources from fixed official TI endpoints.
Usage: py -3 download_models.py --out-dir NEW_DIRECTORY
Refuses to overwrite evidence. audit_models.py consumes download_attempts.json.
"""
import argparse, datetime, hashlib, json, urllib.error, urllib.request, zipfile, io
from pathlib import Path

SAFE_HEADERS={'content-type','content-length','date','last-modified','etag','content-disposition'}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args=parser.parse_args(); root=args.out_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in ['download_attempts.json','slvmda9.zip','slvmau6a.zip']:
        if (root/name).exists(): raise FileExistsError('Preserving existing evidence: '+str(root/name))
    attempts=[]
    for name,url in [('product_page','https://www.ti.com/product/TPS61088'),
                     ('slvmda9','https://www.ti.com/lit/zip/slvmda9'),
                     ('slvmau6a','https://www.ti.com/lit/zip/slvmau6a')]:
        row={'name':name,'requested_url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 TPS61088-model-audit'})
            with urllib.request.urlopen(req,timeout=30) as response:
                data=response.read()
                row.update(status=response.status,final_url=response.url,
                    headers={k:v for k,v in response.headers.items() if k.lower() in SAFE_HEADERS},
                    bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            if name!='product_page':
                row.update(file=name+'.zip',valid_zip_magic=data.startswith(b'PK'))
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    bad=archive.testzip()
                    if bad is not None: raise ValueError('ZIP CRC failure: '+bad)
                (root/(name+'.zip')).write_bytes(data)
        except Exception as exc:
            row['error']=repr(exc)
        attempts.append(row)
        print(json.dumps(row,ensure_ascii=False))
        (root/'download_attempts.json').write_text(json.dumps(attempts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if any(not (root/(name+'.zip')).exists() for name in ['slvmda9','slvmau6a']):
        raise SystemExit('One or more official ZIP downloads failed; inspect download_attempts.json')
if __name__=='__main__': main()
