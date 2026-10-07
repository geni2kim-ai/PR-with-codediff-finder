from __future__ import annotations
import argparse,hashlib,hmac,json,os,time
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from jsonschema import Draft202012Validator
from common import canonical_bytes,object_digest,sha256_file,write_json
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/case-event.schema.json').read_text())
ZERO='0'*64

def utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def canonical_anchor_path(ledger):
    p=Path(ledger)
    return p.with_suffix('.anchor.json') if p.suffix=='.jsonl' else Path(str(p)+'.anchor.json')

# Backward-compatible API name used by v2.5 tools/tests.
def default_anchor_path(ledger):
    return canonical_anchor_path(ledger)

def load_events(path):
    p=Path(path)
    if not p.exists():return []
    out=[]
    for n,line in enumerate(p.read_text(encoding='utf-8').split('\n'),1):
        if line.strip():out.append(json.loads(line))
    return out

def validate_events(events,case_id=None):
    errs=[];prev=ZERO;seq=0
    for ev in events:
        for x in Draft202012Validator(SCHEMA).iter_errors(ev):errs.append(x.message)
        seq+=1
        if ev.get('seq')!=seq:errs.append(f'seq mismatch at {seq}')
        if ev.get('prev_hash')!=prev:errs.append(f'prev_hash mismatch at {seq}')
        if case_id and ev.get('case_id')!=case_id:errs.append(f'case_id mismatch at {seq}')
        if ev.get('event_hash')!=object_digest(ev,'event_hash'):errs.append(f'event_hash mismatch at {seq}')
        prev=ev.get('event_hash',ZERO)
    return errs

@contextmanager
def ledger_lock(path,timeout=10.0):
    lock=Path(str(path)+'.lock');deadline=time.monotonic()+timeout;fd=None
    while True:
        try:
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd);fd=None;break
        except FileExistsError:
            try:
                if time.time()-lock.stat().st_mtime>60:lock.unlink();continue
            except FileNotFoundError:continue
            if time.monotonic()>=deadline:raise TimeoutError(f'ledger lock timeout: {lock}')
            time.sleep(0.02)
    try:yield
    finally:
        try:lock.unlink()
        except FileNotFoundError:pass

def _anchor_core(ledger,case_id,events,key_id=None,schema_version='2.6'):
    p=Path(ledger);last=events[-1]['event_hash'] if events else ZERO
    return {'schema_version':schema_version,'case_id':case_id,'seq':len(events),'event_hash':last,'ledger_sha256':sha256_file(p) if p.exists() else hashlib.sha256(b'').hexdigest(),'key_id':key_id}

def _mac(core,key):return hmac.new(key.encode('utf-8'),canonical_bytes(core),hashlib.sha256).hexdigest()

def write_anchor(ledger,anchor,case_id,events,hmac_key=None,key_id=None):
    core=_anchor_core(ledger,case_id,events,key_id);obj={**core,'hmac_sha256':_mac(core,hmac_key) if hmac_key else None}
    p=Path(anchor);tmp=p.with_suffix(p.suffix+'.tmp');write_json(tmp,obj);os.replace(tmp,p);return obj

def validate_anchor(ledger,anchor,events,case_id=None,hmac_key=None,require_hmac=False):
    p=Path(anchor);errs=[]
    if not p.is_file():return ['ledger anchor missing'] if events or require_hmac else []
    try:a=json.loads(p.read_text())
    except Exception:return ['ledger anchor invalid JSON']
    if a.get('schema_version') not in {'2.4','2.6'}:errs.append('ledger anchor schema mismatch')
    cid=case_id or (events[0]['case_id'] if events else a.get('case_id'))
    core=_anchor_core(ledger,cid,events,a.get('key_id'),a.get('schema_version','2.6'))
    for k,v in core.items():
        if a.get(k)!=v:errs.append(f'anchor {k} mismatch')
    mac=a.get('hmac_sha256')
    if mac and not hmac_key:errs.append('ledger HMAC key unavailable for existing HMAC anchor')
    if require_hmac and not hmac_key:errs.append('ledger HMAC key unavailable')
    if require_hmac and not mac:errs.append('ledger anchor HMAC missing')
    if hmac_key:
        exp=_mac(core,hmac_key)
        if not mac or not hmac.compare_digest(mac,exp):errs.append('ledger anchor HMAC mismatch')
    return errs

def append_event(path,case_id,event_type,payload,timestamp=None,anchor_path=None,hmac_key=None,key_id=None):
    if hmac_key is None:
        hmac_key=os.environ.get('MAESTRO_LEDGER_HMAC_KEY')
        if hmac_key and key_id is None:key_id='MAESTRO_LEDGER_HMAC_KEY'
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);anchor=Path(anchor_path) if anchor_path else canonical_anchor_path(p)
    with ledger_lock(p):
        events=load_events(p);errs=validate_events(events,case_id if events else None)
        if errs:raise ValueError('invalid existing ledger: '+'; '.join(errs))
        if events and not anchor.exists():raise ValueError(f'existing ledger anchor missing: {anchor}')
        if anchor.exists():
            ae=validate_anchor(p,anchor,events,case_id,hmac_key,require_hmac=bool(hmac_key))
            if ae:raise ValueError('invalid existing ledger anchor: '+'; '.join(ae))
        prev=events[-1]['event_hash'] if events else ZERO
        ev={'schema_version':'2.4','case_id':case_id,'seq':len(events)+1,'event_type':event_type,'timestamp':timestamp or utc(),'payload':payload,'prev_hash':prev,'event_hash':''}
        ev['event_hash']=object_digest(ev,'event_hash')
        with p.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(ev,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
        events.append(ev);write_anchor(p,anchor,case_id,events,hmac_key,key_id)
        return ev

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('append');a.add_argument('--ledger',required=True);a.add_argument('--case-id',required=True);a.add_argument('--event-type',required=True);a.add_argument('--payload-json',required=True);a.add_argument('--anchor');a.add_argument('--hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');a.add_argument('--key-id')
    v=sub.add_parser('validate');v.add_argument('--ledger',required=True);v.add_argument('--case-id');v.add_argument('--anchor');v.add_argument('--hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');v.add_argument('--require-hmac',action='store_true')
    ns=ap.parse_args();key=os.environ.get(ns.hmac_key_env)
    if ns.cmd=='append':
        payload=json.loads(Path(ns.payload_json).read_text());print(json.dumps(append_event(ns.ledger,ns.case_id,ns.event_type,payload,anchor_path=ns.anchor,hmac_key=key,key_id=ns.key_id),ensure_ascii=False))
    else:
        events=load_events(ns.ledger);errs=validate_events(events,ns.case_id);anchor=ns.anchor or canonical_anchor_path(ns.ledger);errs+=validate_anchor(ns.ledger,anchor,events,ns.case_id,key,ns.require_hmac)
        if errs:[print('INVALID',x) for x in errs];raise SystemExit(1)
        print('VALID')
if __name__=='__main__':main()
