from __future__ import annotations
import argparse,json,os,re,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from common import object_digest,sha256_file

NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')

def load_spec(path):
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    rows=obj.get('artifacts') if isinstance(obj,dict) else None
    if not isinstance(rows,list) or not rows:raise SystemExit('spec.artifacts must be a non-empty list')
    out=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):raise SystemExit('artifact spec row must be an object')
        name=row.get('name');raw=row.get('path')
        if not isinstance(name,str) or not NAME.fullmatch(name):raise SystemExit('unsafe artifact logical name')
        if name in seen:raise SystemExit(f'duplicate artifact logical name: {name}')
        if not isinstance(raw,str) or not raw:raise SystemExit(f'artifact path missing: {name}')
        p=Path(raw).resolve()
        if not p.is_file():raise SystemExit(f'artifact missing: {name}')
        seen.add(name);out.append((name,p))
    return out

def reject_output_collision(output,spec_path,pre_path=None):
    protected={Path(spec_path).resolve()}
    protected.update(path for _,path in load_spec(spec_path))
    if pre_path is not None:protected.add(Path(pre_path).resolve())
    out=Path(output).resolve()
    if out in protected:raise SystemExit('mutation receipt output collides with protected input')
    return out

def atomic_json(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=p.name+'.',suffix='.tmp',dir=str(p.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        try:Path(tmp).unlink()
        except FileNotFoundError:pass

def capture(spec_path):
    rows=load_spec(spec_path)
    obj={'schema_version':'2.7','kind':'mutation-pre-snapshot','authority_effect':'NONE',
         'items':[{'name':name,'pre_sha256':sha256_file(path)} for name,path in rows],
         'snapshot_digest':''}
    obj['snapshot_digest']=object_digest(obj,'snapshot_digest')
    return obj

def validate_pre(obj):
    if not isinstance(obj,dict) or obj.get('schema_version')!='2.7' or obj.get('kind')!='mutation-pre-snapshot':
        raise SystemExit('invalid mutation pre-snapshot')
    if obj.get('authority_effect')!='NONE':raise SystemExit('mutation pre-snapshot authority_effect must be NONE')
    if obj.get('snapshot_digest')!=object_digest(obj,'snapshot_digest'):raise SystemExit('mutation pre-snapshot digest mismatch')
    items=obj.get('items')
    if not isinstance(items,list) or not items:raise SystemExit('mutation pre-snapshot items missing')
    names=[]
    for row in items:
        if not isinstance(row,dict) or set(row)!={'name','pre_sha256'}:raise SystemExit('invalid mutation pre-snapshot item')
        if not isinstance(row.get('name'),str) or not NAME.fullmatch(row['name']):raise SystemExit('invalid mutation pre-snapshot name')
        if not re.fullmatch(r'[0-9a-f]{64}',str(row.get('pre_sha256',''))):raise SystemExit('invalid mutation pre-snapshot sha256')
        names.append(row['name'])
    if len(names)!=len(set(names)):raise SystemExit('duplicate mutation pre-snapshot name')

def finalize(pre_path,spec_path):
    pre=json.loads(Path(pre_path).read_text(encoding='utf-8'));validate_pre(pre)
    current=load_spec(spec_path);cur={name:path for name,path in current}
    expected={row['name']:row['pre_sha256'] for row in pre['items']}
    if set(cur)!=set(expected):raise SystemExit('mutation receipt artifact set mismatch')
    items=[]
    for name in sorted(expected):
        post=sha256_file(cur[name]);items.append({'name':name,'pre_sha256':expected[name],'post_sha256':post,'equal':post==expected[name]})
    obj={'schema_version':'2.7','kind':'mutation-receipt','authority_effect':'NONE',
         'pre_snapshot_digest':pre['snapshot_digest'],'all_unchanged':all(x['equal'] for x in items),'items':items,'receipt_digest':''}
    obj['receipt_digest']=object_digest(obj,'receipt_digest')
    return obj

def validate_receipt(obj):
    errs=[]
    if not isinstance(obj,dict):return ['mutation receipt must be an object']
    if obj.get('schema_version')!='2.7':errs.append('mutation receipt schema mismatch')
    if obj.get('kind')!='mutation-receipt':errs.append('mutation receipt kind mismatch')
    if obj.get('authority_effect')!='NONE':errs.append('mutation receipt authority_effect must be NONE')
    if not re.fullmatch(r'[0-9a-f]{64}',str(obj.get('pre_snapshot_digest',''))):errs.append('mutation receipt pre_snapshot_digest invalid')
    items=obj.get('items')
    if not isinstance(items,list) or not items:errs.append('mutation receipt items missing');items=[]
    names=[];computed=[]
    for row in items:
        if not isinstance(row,dict) or set(row)!={'name','pre_sha256','post_sha256','equal'}:
            errs.append('invalid mutation receipt item');continue
        name=row.get('name');pre=str(row.get('pre_sha256',''));post=str(row.get('post_sha256',''));eq=row.get('equal')
        if not isinstance(name,str) or not NAME.fullmatch(name):errs.append('invalid mutation receipt name')
        else:names.append(name)
        if not re.fullmatch(r'[0-9a-f]{64}',pre):errs.append(f'invalid pre sha256: {name}')
        if not re.fullmatch(r'[0-9a-f]{64}',post):errs.append(f'invalid post sha256: {name}')
        expected=(pre==post)
        if not isinstance(eq,bool) or eq!=expected:errs.append(f'mutation receipt equality mismatch: {name}')
        computed.append(expected)
    if len(names)!=len(set(names)):errs.append('duplicate mutation receipt name')
    if isinstance(obj.get('all_unchanged'),bool):
        if obj['all_unchanged']!=all(computed):errs.append('mutation receipt all_unchanged mismatch')
    else:errs.append('mutation receipt all_unchanged invalid')
    if obj.get('receipt_digest')!=object_digest(obj,'receipt_digest'):errs.append('mutation receipt digest mismatch')
    return errs

def main():
    ap=argparse.ArgumentParser(description='Create privacy-safe digest-only mutation receipts')
    sub=ap.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('capture');a.add_argument('--spec',required=True);a.add_argument('--output',required=True)
    b=sub.add_parser('finalize');b.add_argument('--pre',required=True);b.add_argument('--spec',required=True);b.add_argument('--output',required=True)
    v=sub.add_parser('validate');v.add_argument('--receipt',required=True)
    ns=ap.parse_args()
    if ns.cmd=='capture':
        out=reject_output_collision(ns.output,ns.spec);atomic_json(out,capture(ns.spec));print('CAPTURED');return
    if ns.cmd=='validate':
        try:obj=json.loads(Path(ns.receipt).read_text(encoding='utf-8'));errs=validate_receipt(obj)
        except Exception as exc:errs=[f'mutation receipt unreadable: {type(exc).__name__}']
        if errs:print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
        print('VALID');return
    out=reject_output_collision(ns.output,ns.spec,ns.pre);obj=finalize(ns.pre,ns.spec);atomic_json(out,obj);print('UNCHANGED' if obj['all_unchanged'] else 'CHANGED')
    if not obj['all_unchanged']:raise SystemExit(2)

if __name__=='__main__':main()
