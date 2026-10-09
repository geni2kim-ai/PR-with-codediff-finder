from __future__ import annotations
import argparse,hashlib,hmac,json,os,socket,tempfile,time,uuid
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from jsonschema import Draft202012Validator
from common import canonical_bytes,object_digest,sha256_file,write_json
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/case-event.schema.json').read_text())
ZERO='0'*64

class LedgerRecoveryError(ValueError):
    pass

class LedgerTornWriteError(LedgerRecoveryError):
    pass


def utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def canonical_anchor_path(ledger):
    p=Path(ledger)
    return p.with_suffix('.anchor.json') if p.suffix=='.jsonl' else Path(str(p)+'.anchor.json')

# Backward-compatible API name used by v2.5 tools/tests.
def default_anchor_path(ledger):
    return canonical_anchor_path(ledger)

def canonical_auth_witness_path(ledger):
    p=Path(ledger)
    return p.with_suffix('.auth.json') if p.suffix=='.jsonl' else Path(str(p)+'.auth.json')

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

def _process_instance_id(pid):
    try:pid=int(pid)
    except Exception:return None
    if pid<=0:return None
    if os.name=='nt':
        try:
            import ctypes
            from ctypes import wintypes
            handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
            if not handle:return None
            try:
                creation=wintypes.FILETIME();exit_time=wintypes.FILETIME();kernel=wintypes.FILETIME();user=wintypes.FILETIME()
                if not ctypes.windll.kernel32.GetProcessTimes(handle,ctypes.byref(creation),ctypes.byref(exit_time),ctypes.byref(kernel),ctypes.byref(user)):
                    return None
                value=(int(creation.dwHighDateTime)<<32)|int(creation.dwLowDateTime)
                return f'win:{value}'
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return None
    proc=Path(f'/proc/{pid}/stat')
    try:raw=proc.read_text(encoding='utf-8')
    except (FileNotFoundError,ProcessLookupError,PermissionError,OSError):
        return None
    rparen=raw.rfind(')')
    if rparen<0:return None
    fields=raw[rparen+2:].split()
    # /proc/<pid>/stat field 22 is process start time; after removing pid+comm,
    # the list starts at field 3, so start time is index 19.
    if len(fields)<=19:return None
    try:boot_id=Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
    except (FileNotFoundError,PermissionError,OSError):boot_id=''
    return f'proc:{boot_id}:{fields[19]}' if boot_id else f'proc:{fields[19]}'

def _stable_machine_identity_source():
    if os.name=='nt':
        try:
            import winreg
            access=winreg.KEY_READ|getattr(winreg,'KEY_WOW64_64KEY',0)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\\Microsoft\\Cryptography',0,access) as key:
                value,_=winreg.QueryValueEx(key,'MachineGuid')
            value=str(value).strip()
            return f'windows-machine-guid:{value}' if value else None
        except Exception:
            return None
    for candidate in (Path('/etc/machine-id'),Path('/var/lib/dbus/machine-id')):
        try:value=candidate.read_text(encoding='utf-8').strip()
        except (FileNotFoundError,PermissionError,OSError):continue
        if value:return f'linux-machine-id:{value}'
    return None

def _lock_component_id(kind,value):
    if value is None:return None
    value=str(value).strip()
    if not value:return None
    explicit=(os.environ.get('MAESTRO_LOCK_HOST_ID') or '').strip()
    material=(explicit+'\0'+kind+'\0'+value) if explicit else (kind+'\0'+value)
    return kind+':'+hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]

def lock_machine_id():
    return _lock_component_id('machine',_stable_machine_identity_source())

def lock_identity_components():
    return {
        'machine_id':lock_machine_id(),
        'hostname_id':_lock_component_id('hostname',socket.gethostname()),
        'node_id':_lock_component_id('node',f'{uuid.getnode():012x}'),
    }

def lock_local_fingerprint():
    return f'{socket.gethostname()}:{uuid.getnode():012x}'

def lock_host_id():
    # MAESTRO_LOCK_HOST_ID is an operator namespace/salt, not a replacement for
    # the local machine fingerprint. Reusing the same configured value on two
    # hosts must not make either host eligible to reclaim the other's live lock.
    local=lock_local_fingerprint()
    explicit=(os.environ.get('MAESTRO_LOCK_HOST_ID') or '').strip()
    if not explicit:return local
    digest=hashlib.sha256((explicit+'\0'+local).encode('utf-8')).hexdigest()[:24]
    return f'{explicit}:{digest}'

def _lock_owner(raw):
    raw=raw.strip()
    if not raw:return None
    try:
        obj=json.loads(raw)
        if isinstance(obj,dict) and isinstance(obj.get('host'),str) and obj.get('host') and isinstance(obj.get('pid'),int) and obj.get('pid')>0 and isinstance(obj.get('token'),str) and obj.get('token'):
            process_instance=obj.get('process_instance')
            if process_instance is not None and (not isinstance(process_instance,str) or not process_instance):
                return None
            for identity_key in ('machine_id','hostname_id','node_id'):
                identity_value=obj.get(identity_key)
                if identity_value is not None and (not isinstance(identity_value,str) or not identity_value):
                    return None
            return obj
    except Exception:
        pass
    # Legacy PID-only locks are intentionally not auto-reclaimed because their
    # host identity is unknowable on shared storage.
    if raw.isdigit():return {'legacy_pid':int(raw)}
    return None

def _same_host_lock_is_stale(existing,host,identity=None):
    if not existing:return False
    same_host=existing.get('host')==host
    if not same_host and identity:
        machine_match=bool(identity.get('machine_id') and existing.get('machine_id')==identity.get('machine_id'))
        hostname_match=bool(identity.get('hostname_id') and existing.get('hostname_id')==identity.get('hostname_id'))
        node_match=bool(identity.get('node_id') and existing.get('node_id')==identity.get('node_id'))
        same_host=machine_match and (hostname_match or node_match)
    if not same_host:return False
    pid=existing.get('pid')
    expected_instance=existing.get('process_instance')
    observed_instance=_process_instance_id(pid)
    if expected_instance and observed_instance is not None:
        return expected_instance!=observed_instance
    return not _pid_alive(pid)

def _unlink_lock_if_unchanged(lock,expected_raw):
    try:
        current=lock.read_text(encoding='utf-8')
        if current!=expected_raw:return False
        lock.unlink();return True
    except FileNotFoundError:return False

def _reclaim_stale_lock(lock,host,identity=None):
    # Stale reclamation needs its own atomic guard. Without this, two
    # reclaimers can both validate an old lock; one may then delete the fresh
    # lock installed by the other between compare and unlink.
    guard=Path(str(lock)+'.reclaim')
    try:guard.mkdir(mode=0o700)
    except FileExistsError:return False
    try:
        try:raw=lock.read_text(encoding='utf-8')
        except FileNotFoundError:return False
        existing=_lock_owner(raw)
        if not _same_host_lock_is_stale(existing,host,identity):return False
        return _unlink_lock_if_unchanged(lock,raw)
    finally:
        try:guard.rmdir()
        except OSError:pass

@contextmanager
def ledger_lock(path,timeout=10.0):
    lock=Path(str(path)+'.lock');lock.parent.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+timeout;fd=None
    host=lock_host_id();identity=lock_identity_components();token=f'{os.getpid()}-{time.time_ns()}'
    owner={'schema_version':'2.7','host':host,'pid':os.getpid(),'token':token}
    owner.update({k:v for k,v in identity.items() if v is not None})
    process_instance=_process_instance_id(os.getpid())
    if process_instance is not None:owner['process_instance']=process_instance
    encoded=(json.dumps(owner,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    while True:
        try:
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            try:
                with os.fdopen(fd,'wb',closefd=True) as f:
                    fd=None;f.write(encoded);f.flush();os.fsync(f.fileno())
            except Exception:
                if fd is not None:
                    try:os.close(fd)
                    except OSError:pass
                    fd=None
                try:lock.unlink()
                except FileNotFoundError:pass
                raise
            break
        except FileExistsError:
            try:
                raw=lock.read_text(encoding='utf-8')
                existing=_lock_owner(raw)
                if _same_host_lock_is_stale(existing,host,identity) and _reclaim_stale_lock(lock,host,identity):continue
            except FileNotFoundError:
                continue
            if time.monotonic()>=deadline:raise TimeoutError(f'ledger lock timeout: {lock}')
            time.sleep(0.02)
    try:yield
    finally:
        try:
            raw=lock.read_text(encoding='utf-8')
            existing=_lock_owner(raw)
            if existing and existing.get('host')==host and existing.get('pid')==os.getpid() and existing.get('token')==token:
                _unlink_lock_if_unchanged(lock,raw)
        except FileNotFoundError:pass

def ensure_control_dir(path):
    p=Path(path)
    if p.exists() or p.is_symlink():
        is_junction=getattr(p,'is_junction',lambda:False)()
        if p.is_symlink() or is_junction or not p.is_dir():
            raise ValueError(f'unsafe coordination directory: {p}')
    else:
        p.mkdir(mode=0o700,parents=True,exist_ok=False)
    # Re-check after creation/lookup so a pre-existing redirect never becomes an
    # accepted lock namespace.
    is_junction=getattr(p,'is_junction',lambda:False)()
    if p.is_symlink() or is_junction or not p.is_dir():
        raise ValueError(f'unsafe coordination directory: {p}')
    try:os.chmod(p,0o700)
    except OSError:pass
    return p

def case_bundle_lock_path(case_path):
    p=Path(case_path)
    base=ensure_control_dir(p.parent/'.codediff-control')
    token=hashlib.sha256(p.name.encode('utf-8')).hexdigest()[:16]
    return base/f'case-bundle-{token}'

@contextmanager
def case_bundle_lock(case_path,timeout=10.0):
    target=case_bundle_lock_path(case_path)
    # The shared control directory is intentionally persistent. Removing it on
    # unlock races with waiters on another process/host that are about to create
    # the next lock file.
    with ledger_lock(target,timeout=timeout):
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

def _auth_witness_digest(obj):
    return object_digest({k:v for k,v in obj.items() if k!='witness_digest'})

def load_auth_witness(ledger,case_id=None):
    path=canonical_auth_witness_path(ledger)
    if not path.is_file():return None
    try:obj=json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:raise ValueError(f'ledger auth witness unreadable: {type(exc).__name__}') from exc
    expected={'schema_version','kind','case_id','hmac_required','key_id','witness_digest'}
    if set(obj)!=expected:raise ValueError('ledger auth witness fields mismatch')
    if obj.get('schema_version')!='2.7' or obj.get('kind')!='ledger-auth-witness':raise ValueError('ledger auth witness schema/kind mismatch')
    if not isinstance(obj.get('case_id'),str) or not obj.get('case_id'):raise ValueError('ledger auth witness case_id invalid')
    if case_id is not None and obj.get('case_id')!=case_id:raise ValueError('ledger auth witness case_id mismatch')
    if type(obj.get('hmac_required')) is not bool:raise ValueError('ledger auth witness hmac_required invalid')
    if obj.get('key_id') is not None and (not isinstance(obj.get('key_id'),str) or not obj.get('key_id')):raise ValueError('ledger auth witness key_id invalid')
    if obj.get('witness_digest')!=_auth_witness_digest(obj):raise ValueError('ledger auth witness digest mismatch')
    return obj

def ensure_auth_witness(ledger,case_id,hmac_required,key_id=None):
    path=canonical_auth_witness_path(ledger);existing=load_auth_witness(ledger,case_id)
    required=bool(hmac_required) or bool(existing and existing.get('hmac_required'))
    effective_key_id=(existing or {}).get('key_id') or key_id
    if existing and existing.get('hmac_required')==required and existing.get('key_id')==effective_key_id:return existing
    obj={'schema_version':'2.7','kind':'ledger-auth-witness','case_id':case_id,'hmac_required':required,'key_id':effective_key_id,'witness_digest':''}
    obj['witness_digest']=_auth_witness_digest(obj);_atomic_json_fsync(path,obj);return obj

def _witness_requires_hmac(ledger,case_id=None):
    obj=load_auth_witness(ledger,case_id)
    return bool(obj and obj.get('hmac_required'))

def _repair_exact_torn_tail(ledger,event,pre_ledger_sha256):
    p=Path(ledger);raw=p.read_bytes() if p.exists() else b'';event_bytes=_events_bytes([event])
    if hashlib.sha256(raw).hexdigest()==pre_ledger_sha256:return False
    if len(raw)>=len(event_bytes) and raw.endswith(event_bytes) and hashlib.sha256(raw[:-len(event_bytes)]).hexdigest()==pre_ledger_sha256:return False
    limit=min(len(raw),max(0,len(event_bytes)-1))
    for size in range(limit,0,-1):
        if raw.endswith(event_bytes[:size]) and hashlib.sha256(raw[:-size]).hexdigest()==pre_ledger_sha256:
            with p.open('r+b') as fh:
                fh.truncate(len(raw)-size);fh.flush();os.fsync(fh.fileno())
            return True
    return False

def _append_tx_digest(tx):
    core={k:v for k,v in tx.items() if k not in {'transaction_digest','hmac_sha256'}}
    return object_digest(core)

def _append_tx_mac(tx,key):
    core={k:v for k,v in tx.items() if k!='hmac_sha256'}
    return _mac(core,key)

def _validate_append_tx(tx,hmac_key=None,require_hmac=False):
    errs=[]
    if tx.get('schema_version') not in {'2.6','2.7'}:errs.append('append transaction schema mismatch')
    if tx.get('transaction_digest')!=_append_tx_digest(tx):errs.append('append transaction digest mismatch')
    mac=tx.get('hmac_sha256')
    event_instance_id=tx.get('event_instance_id')
    if event_instance_id is not None and (not isinstance(event_instance_id,str) or not event_instance_id or len(event_instance_id)>256):errs.append('append transaction event_instance_id invalid')
    if mac and not hmac_key:errs.append('append transaction HMAC key unavailable')
    if require_hmac and not hmac_key:errs.append('append transaction HMAC key unavailable')
    if require_hmac and not mac:errs.append('append transaction HMAC missing')
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

def _recover_pending_append(ledger,anchor,tx_path,hmac_key=None,require_hmac=False):
    try:tx=json.loads(Path(tx_path).read_text(encoding='utf-8'))
    except Exception as exc:raise LedgerRecoveryError(f'append transaction unreadable: {type(exc).__name__}') from exc
    effective_require=bool(require_hmac) or _witness_requires_hmac(ledger,tx.get('case_id'))
    errs=_validate_append_tx(tx,hmac_key,effective_require)
    if errs:raise LedgerRecoveryError('invalid append transaction: '+'; '.join(errs))
    p=Path(ledger);n=int(tx['pre_seq']);ev=tx['event']
    _repair_exact_torn_tail(p,ev,tx.get('pre_ledger_sha256'))
    try:events=load_events(p)
    except (json.JSONDecodeError,UnicodeDecodeError) as exc:
        raise LedgerTornWriteError('ledger tail is malformed and does not match the pending append transaction') from exc
    errs=validate_events(events,tx['case_id'])
    if errs:raise LedgerRecoveryError('invalid ledger during append recovery: '+'; '.join(errs))
    pre_events=events[:n]
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
    ev=tx.get('event')
    if not isinstance(ev,dict):raise ValueError('append transaction event missing')
    cid=tx.get('case_id')
    if not isinstance(cid,str) or not cid:raise ValueError('append transaction case_id missing')
    mac=tx.get('hmac_sha256');require_hmac=bool(require_hmac) or _witness_requires_hmac(ledger,cid)
    if mac and not hmac_key:raise ValueError('append transaction HMAC key unavailable')
    if require_hmac and not hmac_key:raise ValueError('append transaction HMAC key unavailable')
    if require_hmac and not mac:raise ValueError('append transaction HMAC missing')
    if hmac_key and mac and not hmac.compare_digest(mac,_append_tx_mac(tx,hmac_key)):raise ValueError('append transaction HMAC mismatch')
    if ev.get('case_id')!=cid:raise ValueError('append transaction case_id mismatch')
    if ev.get('event_hash')!=object_digest(ev,'event_hash'):raise ValueError('append transaction event hash mismatch')
    try:pre_seq=int(tx.get('pre_seq',-1))
    except Exception as exc:raise ValueError('append transaction pre_seq invalid') from exc
    if ev.get('seq')!=pre_seq+1:raise ValueError('append transaction seq mismatch')
    if ev.get('prev_hash')!=tx.get('pre_event_hash'):raise ValueError('append transaction prev_hash mismatch')
    return cid

def recover_pending_append_if_present(ledger,anchor_path=None,hmac_key=None,require_hmac=False):
    p=Path(ledger);anchor=Path(anchor_path) if anchor_path else canonical_anchor_path(p);tx_path=pending_append_path(p)
    if not tx_path.exists():return False
    with ledger_lock(p):
        if not tx_path.exists():return False
        _recover_pending_append(p,anchor,tx_path,hmac_key,require_hmac)
    return True

def write_anchor(ledger,anchor,case_id,events,hmac_key=None,key_id=None):
    core=_anchor_core(ledger,case_id,events,key_id);obj={**core,'hmac_sha256':_mac(core,hmac_key) if hmac_key else None}
    p=Path(anchor);tmp=p.with_suffix(p.suffix+'.tmp');write_json(tmp,obj);os.replace(tmp,p);return obj

def validate_anchor(ledger,anchor,events,case_id=None,hmac_key=None,require_hmac=False):
    p=Path(anchor);errs=[]
    try:require_hmac=bool(require_hmac) or _witness_requires_hmac(ledger,case_id)
    except ValueError as exc:errs.append(str(exc))
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

def append_event(path,case_id,event_type,payload,timestamp=None,anchor_path=None,hmac_key=None,key_id=None,event_instance_id=None):
    if hmac_key is None:
        hmac_key=os.environ.get('MAESTRO_LEDGER_HMAC_KEY')
        if hmac_key and key_id is None:key_id='MAESTRO_LEDGER_HMAC_KEY'
    if event_instance_id is not None and (not isinstance(event_instance_id,str) or not event_instance_id or len(event_instance_id)>256):
        raise ValueError('event_instance_id must be a non-empty string up to 256 chars')
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);anchor=Path(anchor_path) if anchor_path else canonical_anchor_path(p);tx_path=pending_append_path(p)
    with ledger_lock(p):
        visible_anchor_hmac=False
        if anchor.is_file():
            try:visible_anchor_hmac=bool(json.loads(anchor.read_text(encoding='utf-8')).get('hmac_sha256'))
            except Exception:pass
        witness=ensure_auth_witness(p,case_id,bool(hmac_key) or visible_anchor_hmac,key_id)
        require_hmac=bool(witness.get('hmac_required'))
        if require_hmac and not hmac_key:raise ValueError('ledger HMAC key unavailable for signed-history witness')
        if tx_path.exists():
            try:pending_tx=json.loads(tx_path.read_text(encoding='utf-8'))
            except Exception as exc:raise LedgerRecoveryError(f'append transaction unreadable: {type(exc).__name__}') from exc
            recovered=_recover_pending_append(p,anchor,tx_path,hmac_key,require_hmac)
            if event_instance_id is not None and pending_tx.get('event_instance_id')==event_instance_id:
                return recovered
            if 'event_instance_id' not in pending_tx and recovered.get('case_id')==case_id and recovered.get('event_type')==event_type and recovered.get('payload')==payload:
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
        tx={'schema_version':'2.7','case_id':case_id,'pre_seq':len(events),'pre_event_hash':prev,'pre_ledger_sha256':_file_sha_or_empty(p),'key_id':key_id,'event_instance_id':event_instance_id,'event':ev}
        tx['transaction_digest']=_append_tx_digest(tx);tx['hmac_sha256']=_append_tx_mac(tx,hmac_key) if hmac_key else None
        _atomic_json_fsync(tx_path,tx)
        with p.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(ev,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
        events.append(ev);write_anchor(p,anchor,case_id,events,hmac_key,key_id);tx_path.unlink(missing_ok=True)
        return ev

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('append');a.add_argument('--ledger',required=True);a.add_argument('--case-id',required=True);a.add_argument('--event-type',required=True);a.add_argument('--payload-json',required=True);a.add_argument('--anchor');a.add_argument('--hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');a.add_argument('--key-id');a.add_argument('--event-instance-id')
    v=sub.add_parser('validate');v.add_argument('--ledger',required=True);v.add_argument('--case-id');v.add_argument('--anchor');v.add_argument('--hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');v.add_argument('--require-hmac',action='store_true')
    ns=ap.parse_args();key=os.environ.get(ns.hmac_key_env)
    if ns.cmd=='append':
        payload=json.loads(Path(ns.payload_json).read_text());print(json.dumps(append_event(ns.ledger,ns.case_id,ns.event_type,payload,anchor_path=ns.anchor,hmac_key=key,key_id=ns.key_id,event_instance_id=ns.event_instance_id),ensure_ascii=False))
    else:
        events=load_events(ns.ledger);errs=validate_events(events,ns.case_id);anchor=ns.anchor or canonical_anchor_path(ns.ledger);errs+=validate_anchor(ns.ledger,anchor,events,ns.case_id,key,ns.require_hmac)
        if errs:[print('INVALID',x) for x in errs];raise SystemExit(1)
        print('VALID')
if __name__=='__main__':main()
