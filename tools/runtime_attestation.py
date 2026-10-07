from __future__ import annotations
import argparse,hashlib,hmac,json,os,re,secrets
from datetime import datetime,timezone
from pathlib import Path
from common import canonical_bytes,write_json,object_digest


def utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def mac(core,key):return hmac.new(key.encode(),canonical_bytes(core),hashlib.sha256).hexdigest()
def _dt(s):
    if not isinstance(s,str) or not s:return None
    try:return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:return None

def replay_token(obj):
    fields={k:obj.get(k) for k in ('key_id','nonce','case_id','base_sha','head_sha','workspace','issued_at')}
    return hashlib.sha256(canonical_bytes(fields)).hexdigest()

def consume_nonce(obj,replay_dir):
    nonce=obj.get('nonce')
    if not isinstance(nonce,str) or not re.fullmatch(r'[0-9a-f]{32}',nonce):
        return 'runtime attestation nonce invalid',None
    root=Path(replay_dir).resolve()
    try:
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        token=replay_token(obj);path=root/(token+'.used')
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
        fd=os.open(path,flags,0o600)
        try:
            payload=canonical_bytes({'replay_token':token,'attestation_digest':object_digest(obj)})
            os.write(fd,payload);os.fsync(fd)
        finally:os.close(fd)
        return None,token
    except FileExistsError:
        return 'runtime attestation replay detected',replay_token(obj)
    except OSError as exc:
        return f'runtime attestation replay cache unavailable: {type(exc).__name__}',None

def create(workspace,key,key_id='external-launcher',case_id=None,base_sha=None,head_sha=None,*,l2_fresh_session=True,adversarial_fresh_session=True):
    core={'schema_version':'2.6','workspace':str(Path(workspace).resolve()),'environment_secret_stripping':True,'network_denied':True,'filesystem_scoped_to_workspace':True,
          'l2_fresh_session':bool(l2_fresh_session),'adversarial_fresh_session':bool(adversarial_fresh_session),
          'case_id':case_id,'base_sha':base_sha,'head_sha':head_sha,'issued_at':utc(),'nonce':secrets.token_hex(16),'key_id':key_id}
    return {**core,'attestation_hmac':mac(core,key)}

def validate(obj,workspace,key,required_fields=None,*,case_id=None,base_sha=None,head_sha=None,max_age_seconds=300,max_future_skew_seconds=5,now=None):
    e=[];core={k:v for k,v in obj.items() if k!='attestation_hmac'}
    if obj.get('schema_version') not in {'2.4','2.6'}:e.append('runtime attestation schema mismatch')
    if obj.get('workspace')!=str(Path(workspace).resolve()):e.append('runtime attestation workspace mismatch')
    if not isinstance(obj.get('nonce'),str) or not re.fullmatch(r'[0-9a-f]{32}',obj.get('nonce','')):e.append('runtime attestation nonce invalid')
    required_fields=tuple(required_fields or ('environment_secret_stripping','network_denied','filesystem_scoped_to_workspace'))
    for k in required_fields:
        if obj.get(k) is not True:e.append(f'runtime attestation missing {k}=true')
    if case_id is not None and obj.get('case_id')!=case_id:e.append('runtime attestation case_id mismatch')
    if base_sha is not None and obj.get('base_sha')!=base_sha:e.append('runtime attestation base_sha mismatch')
    if head_sha is not None and obj.get('head_sha')!=head_sha:e.append('runtime attestation head_sha mismatch')
    issued=_dt(obj.get('issued_at'));now_dt=now if isinstance(now,datetime) else datetime.now(timezone.utc)
    if issued is None:e.append('runtime attestation issued_at invalid')
    else:
        age=(now_dt-issued).total_seconds()
        if age>float(max_age_seconds):e.append('runtime attestation stale')
        if age < -float(max_future_skew_seconds):e.append('runtime attestation issued_at too far in future')
    if not key:e.append('runtime attestation HMAC key unavailable')
    elif not obj.get('attestation_hmac') or not hmac.compare_digest(obj['attestation_hmac'],mac(core,key)):e.append('runtime attestation HMAC mismatch')
    return e

def digest(obj):return object_digest(obj)

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create');c.add_argument('--workspace',required=True);c.add_argument('--output',required=True);c.add_argument('--key-env',default='MAESTRO_RUNTIME_ATTESTATION_KEY');c.add_argument('--key-id',default='external-launcher');c.add_argument('--case-id');c.add_argument('--base-sha');c.add_argument('--head-sha');c.add_argument('--no-l2-fresh-session',action='store_true');c.add_argument('--no-adversarial-fresh-session',action='store_true')
    v=sub.add_parser('validate');v.add_argument('--workspace',required=True);v.add_argument('--attestation',required=True);v.add_argument('--key-env',default='MAESTRO_RUNTIME_ATTESTATION_KEY');v.add_argument('--case-id');v.add_argument('--base-sha');v.add_argument('--head-sha');v.add_argument('--max-age-seconds',type=int,default=300);v.add_argument('--max-future-skew-seconds',type=int,default=5)
    ns=ap.parse_args();key=os.environ.get(ns.key_env)
    if not key:raise SystemExit(f'missing {ns.key_env}')
    if ns.cmd=='create':write_json(ns.output,create(ns.workspace,key,ns.key_id,ns.case_id,ns.base_sha,ns.head_sha,l2_fresh_session=not ns.no_l2_fresh_session,adversarial_fresh_session=not ns.no_adversarial_fresh_session));print(ns.output)
    else:
        o=json.loads(Path(ns.attestation).read_text());errs=validate(o,ns.workspace,key,case_id=ns.case_id,base_sha=ns.base_sha,head_sha=ns.head_sha,max_age_seconds=ns.max_age_seconds,max_future_skew_seconds=ns.max_future_skew_seconds)
        if errs:print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
        print('VALID')
if __name__=='__main__':main()
