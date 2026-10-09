from __future__ import annotations
import argparse,hashlib,hmac,json,os,tempfile,time
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

def _pid_alive(pid):
    try:pid=int(pid)
    except Exception:return False
    if pid<=0:return False
    if pid==os.getpid():return True
    if os.name=='nt':
        try:
            import ctypes
            handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
            if not handle:return False
            ctypes.windll.kernel32.CloseHandle(handle);return True
        except Exception:return True
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

@contextmanager
def ledger_lock(path,timeout=10.0):
    lock=Path(str(path)+'.lock');deadline=time.monotonic()+timeout;fd=None
    while True:
        try:
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd);fd=None;break
        except FileExistsError:
            try:
                raw=lock.read_text(encoding='utf-8').strip()
                owner=int(raw) if raw else None
                if owner is not None and not _pid_alive(owner):lock.unlink();continue
                if owner is None and time.time()-lock.stat().st_mtime>max(1.0,timeout):lock.unlink();continue
            except (FileNotFoundError,ValueError): 
                try:
                    if lock.exists() and time.time()-lock.stat().st_mtime>max(1.0,timeout):lock.unlink();continue
                except FileNotFoundError:continue
            if time.monotonic()>=deadline:raise TimeoutError(f'ledger lock timeout: {lock}')
            time.sleep(0.02)
    try:yield
    finally:
        try:lock.unlink()
        except FileNotFoundError:pass

def case_bundle_lock_path(case_path):
    base=Path(tempfile.gettempdir())/'codediff-finder-bundle-locks'
    base.mkdir(mode=0o700,parents=True,exist_ok=True)
    try:os.chmod(base,0o700)
    except OSError:pass
    token=hashlib.sha256(str(Path(case_path).resolve()).encode('utf-8')).hexdigest()[:32]
    return base/token

@contextmanager
def case_bundle_lock(case_path,timeout=10.0):
    with ledger_lock(case_bundle_lock_path(case_path),timeout=timeout):
        yield

def _anchor_core(ledger,case_id,events,key_id=None,schema_version='2.7'):
    p=Path(ledger);last=events[-1]['event_hash'] if events else ZERO
    return {'schema_version':schema_version,'case_id':case_id,'seq':len(events),'event_hash':last,'ledger_sha256':sha256_file(p) if p.exists() else hashlib.sha256(b'').hexdigest(),'key_id':key_id}

def _mac(core,key):return hmac.new(key.encode('utf-8'),canonical_bytes(core),hashlib.sha256).hexdigest()

def pending_append_path(ledger):
    return Path(str(ledger)+'.append-transaction.json')

def _events_bytes(events):
    return b''.join((json.dumps(ev,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8') for ev in events)

def _events_sha256(events):
    return hashlib.sha256(_events_bytes(events)).hexdigest()

def _file_sha_or_empty(path):
    p=Path(path)
    return sha256_file(p) if p.exists() else hashlib.sha256(b'').hexdigest()

def _pre_ledger_sha256_from_current(ledger,event,pre_seq,current_len):
    p=Path(ledger);raw=p.read_bytes() if p.exists() else b''
    if current_len==pre_seq:return hashlib.sha256(raw).hexdigest()
    if current_len==pre_seq+1:
        tail=_events_bytes([event])
        if not raw.endswith(tail):raise ValueError('append transaction raw ledger tail mismatch')
        return hashlib.sha256(raw[:-len(tail)]).hexdigest()
    raise ValueError('append transaction ledger length mismatch')

def _atomic_json_fsync(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=Path(str(p)+'.tmp')
    data=(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    with tmp.open('wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

def _append_tx_digest(tx):
    core={k:v for k,v in tx.items() if k not in {'transaction_digest','hmac_sha256'}}
    return object_digest(core)

def _append_tx_mac(tx,key):
    core={k:v for k,v in tx.items() if k!='hmac_sha256'}
    return _mac(core,key)

def _validate_append_tx(tx,hmac_key=None):
    errs=[]
    if tx.get('schema_version') not in {'2.6','2.7'}:errs.append('append transaction schema mismatch')
    if tx.get('transaction_digest')!=_append_tx_digest(tx):errs.append('append transaction digest mismatch')
    mac=tx.get('hmac_sha256')
    if mac and not hmac_key:errs.append('append transaction HMAC key unavailable')
    if hmac_key:
        if not mac:errs.append('append transaction HMAC missing')
        elif not hmac.compare_digest(mac,_append_tx_mac(tx,hmac_key)):errs.append('append transaction HMAC mismatch')
    ev=tx.get('event')
    if not isinstance(ev,dict):errs.append('append transaction event missing')
    else:
        if ev.get('event_hash')!=object_digest(ev,'event_hash'):errs.append('append transaction event hash mismatch')
        if ev.get('case_id')!=tx.get('case_id'):errs.append('append transaction case_id mismatch')
        if ev.get('seq')!=int(tx.get('pre_seq',-1))+1:errs.append('append transaction seq mismatch')
        if ev.get('prev_hash')!=tx.get('pre_event_hash'):errs.append('append transaction prev_hash mismatch')
    return errs

def _recover_pending_append(ledger,anchor,tx_path,hmac_key=None):
    try:tx=json.loads(Path(tx_path).read_text(encoding='utf-8'))
    except Exception as exc:raise ValueError(f'append transaction unreadable: {type(exc).__name__}') from exc
    errs=_validate_append_tx(tx,hmac_key)
    if errs:raise ValueError('invalid append transaction: '+'; '.join(errs))
    p=Path(ledger);events=load_events(p);errs=validate_events(events,tx['case_id'])
    if errs:raise ValueError('invalid ledger during append recovery: '+'; '.join(errs))
    n=int(tx['pre_seq']);ev=tx['event'];pre_events=events[:n]
    if len(events)<n or _pre_ledger_sha256_from_current(p,ev,n,len(events))!=tx.get('pre_ledger_sha256'):
        raise ValueError('append transaction pre-ledger mismatch')
    pre_hash=pre_events[-1]['event_hash'] if pre_events else ZERO
    if pre_hash!=tx.get('pre_event_hash'):raise ValueError('append transaction pre-hash mismatch')
    if len(events)==n:
        with p.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(ev,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
        events.append(ev)
    elif len(events)==n+1 and events[-1]==ev:
        pass
    else:
        raise ValueError('append transaction ledger divergence')
    write_anchor(p,anchor,tx['case_id'],events,hmac_key,tx.get('key_id'))
    Path(tx_path).unlink(missing_ok=True)
    return ev

def pending_append_case_id(ledger,hmac_key=None,require_hmac=False):
    tx_path=pending_append_path(ledger)
    if not tx_path.is_file():return None
    try:tx=json.loads(tx_path.read_text(encoding='utf-8'))
    except Exception as exc:raise ValueError(f'append transaction unreadable: {type(exc).__name__}') from exc
    # Classification validates the self-contained transaction/event structure.
    # If the active campaign supplies HMAC authority, a shared root is treated as
    # one HMAC trust domain so relabeling an active transaction cannot turn it
    # into an unauthenticated "unrelated" record.
    core={k:v for k,v in tx.items() if k not in {'transaction_digest','hmac_sha256'}}
    if tx.get('transaction_digest')!=object_digest(core):raise ValueError('append transaction digest mismatch')
    mac=tx.get('hmac_sha256')
    if mac and not hmac_key:raise ValueError('append transaction HMAC key unavailable')
    if require_hmac and not mac:raise ValueError('append transaction HMAC missing')
    if hmac_key and mac and not hmac.compare_digest(mac,_append_tx_mac(tx,hmac_key)):raise ValueError('append transaction HMAC mismatch')
    ev=tx.get('event')
    if not isinstance(ev,dict):raise ValueError('append transaction event missing')
    cid=tx.get('case_id')
    if not isinstance(cid,str) or not cid:raise ValueError('append transaction case_id missing')
    if ev.get('case_id')!=cid:raise ValueError('append transaction case_id mismatch')
    if ev.get('event_hash')!=object_digest(ev,'event_hash'):raise ValueError('append transaction event hash mismatch')
    try:pre_seq=int(tx.get('pre_seq',-1))
    except Exception as exc:raise ValueError('append transaction pre_seq invalid') from exc
    if ev.get('seq')!=pre_seq+1:raise ValueError('append transaction seq mismatch')
    if ev.get('prev_hash')!=tx.get('pre_event_hash'):raise ValueError('append transaction prev_hash mismatch')
    return cid

def recover_pending_append_if_present(ledger,anchor_path=None,hmac_key=None):
    p=Path(ledger);anchor=Path(anchor_path) if anchor_path else canonical_anchor_path(p);tx_path=pending_append_path(p)
    if not tx_path.exists():return False
    with ledger_lock(p):
        if not tx_path.exists():return False
        _recover_pending_append(p,anchor,tx_path,hmac_key)
    return True

def write_anchor(ledger,anchor,case_id,events,hmac_key=None,key_id=None):
    core=_anchor_core(ledger,case_id,events,key_id);obj={**core,'hmac_sha256':_mac(core,hmac_key) if hmac_key else None}
    p=Path(anchor);tmp=p.with_suffix(p.suffix+'.tmp');write_json(tmp,obj);os.replace(tmp,p);return obj

def validate_anchor(ledger,anchor,events,case_id=None,hmac_key=None,require_hmac=False):
    p=Path(anchor);errs=[]
    if not p.is_file():return ['ledger anchor missing'] if events or require_hmac else []
    try:a=json.loads(p.read_text())
    except Exception:return ['ledger anchor invalid JSON']
    if a.get('schema_version') not in {'2.4','2.6','2.7'}:errs.append('ledger anchor schema mismatch')
    cid=case_id or (events[0]['case_id'] if events else a.get('case_id'))
    core=_anchor_core(ledger,cid,events,a.get('key_id'),a.get('schema_version','2.7'))
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
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);anchor=Path(anchor_path) if anchor_path else canonical_anchor_path(p);tx_path=pending_append_path(p)
    with ledger_lock(p):
        if tx_path.exists():
            recovered=_recover_pending_append(p,anchor,tx_path,hmac_key)
            if recovered.get('case_id')==case_id and recovered.get('event_type')==event_type and recovered.get('payload')==payload:
                return recovered
        ledger_preexisting=p.exists()
        events=load_events(p);errs=validate_events(events,case_id if events else None)
        if errs:raise ValueError('invalid existing ledger: '+'; '.join(errs))
        # A pre-existing ledger file must have an anchor even if it was truncated to
        # zero bytes. Otherwise "truncate ledger + delete anchor" is indistinguishable
        # from a brand-new history and silently resets seq/hash state.
        if ledger_preexisting and not anchor.exists():raise ValueError(f'existing ledger anchor missing: {anchor}')
        if anchor.exists():
            ae=validate_anchor(p,anchor,events,case_id,hmac_key,require_hmac=bool(hmac_key))
            if ae:raise ValueError('invalid existing ledger anchor: '+'; '.join(ae))
        prev=events[-1]['event_hash'] if events else ZERO
        ev={'schema_version':'2.4','case_id':case_id,'seq':len(events)+1,'event_type':event_type,'timestamp':timestamp or utc(),'payload':payload,'prev_hash':prev,'event_hash':''}
        ev['event_hash']=object_digest(ev,'event_hash')
        tx={'schema_version':'2.7','case_id':case_id,'pre_seq':len(events),'pre_event_hash':prev,'pre_ledger_sha256':_file_sha_or_empty(p),'key_id':key_id,'event':ev}
        tx['transaction_digest']=_append_tx_digest(tx);tx['hmac_sha256']=_append_tx_mac(tx,hmac_key) if hmac_key else None
        _atomic_json_fsync(tx_path,tx)
        with p.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(ev,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
        events.append(ev);write_anchor(p,anchor,case_id,events,hmac_key,key_id);tx_path.unlink(missing_ok=True)
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
