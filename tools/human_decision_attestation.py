from __future__ import annotations
import argparse,hashlib,hmac,json,os,re,secrets
from datetime import datetime,timezone
from pathlib import Path
from common import canonical_bytes,object_digest,write_json

def utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def _mac(core,key):return hmac.new(key.encode('utf-8'),canonical_bytes(core),hashlib.sha256).hexdigest()
def _dt(s):
    if not isinstance(s,str) or not s:return None
    try:return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:return None

def create(case_id,actor_id,verdict,head_sha,key,cycle_digest,evidence_digest,key_id='external-human-authority'):
    core={'schema_version':'2.6','case_id':case_id,'actor_id':actor_id,'verdict':verdict,'head_sha':head_sha,
          'cycle_digest':cycle_digest,'evidence_digest':evidence_digest,
          'issued_at':utc(),'nonce':secrets.token_hex(16),'key_id':key_id}
    return {**core,'attestation_hmac':_mac(core,key)}

def validate(obj,*,case_id,actor_id,verdict,head_sha,cycle_digest,evidence_digest,key,max_age_seconds=300,max_future_skew_seconds=5):
    e=[];core={k:v for k,v in obj.items() if k!='attestation_hmac'}
    if obj.get('schema_version')!='2.6':e.append('human attestation schema mismatch')
    if obj.get('case_id')!=case_id:e.append('human attestation case_id mismatch')
    if obj.get('actor_id')!=actor_id:e.append('human attestation actor_id mismatch')
    if obj.get('verdict')!=verdict:e.append('human attestation verdict mismatch')
    if obj.get('head_sha')!=head_sha:e.append('human attestation head_sha mismatch')
    if obj.get('cycle_digest')!=cycle_digest:e.append('human attestation cycle_digest mismatch')
    if obj.get('evidence_digest')!=evidence_digest:e.append('human attestation evidence_digest mismatch')
    if not isinstance(obj.get('nonce'),str) or not re.fullmatch(r'[0-9a-f]{32}',obj.get('nonce','')):e.append('human attestation nonce invalid')
    issued=_dt(obj.get('issued_at'));now=datetime.now(timezone.utc)
    if issued is None:e.append('human attestation issued_at invalid')
    else:
        age=(now-issued).total_seconds()
        if age>float(max_age_seconds):e.append('human attestation stale')
        if age < -float(max_future_skew_seconds):e.append('human attestation issued_at too far in future')
    if not key:e.append('human attestation HMAC key unavailable')
    elif not obj.get('attestation_hmac') or not hmac.compare_digest(obj['attestation_hmac'],_mac(core,key)):e.append('human attestation HMAC mismatch')
    return e

def replay_token(obj):
    return hashlib.sha256(canonical_bytes({k:obj.get(k) for k in ('key_id','nonce','case_id','actor_id','verdict','head_sha','cycle_digest','evidence_digest')})).hexdigest()

def consume_nonce(obj,replay_dir,transaction_id):
    root=Path(replay_dir).resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=replay_token(obj);path=root/(token+'.used');marker={'transaction_id':transaction_id,'attestation_digest':object_digest(obj)}
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:os.write(fd,canonical_bytes(marker));os.fsync(fd)
        finally:os.close(fd)
        return None,token
    except FileExistsError:
        try:existing=json.loads(path.read_text())
        except Exception:return 'human attestation replay marker unreadable',token
        if existing==marker:return None,token
        return 'human attestation replay detected',token
    except OSError as exc:
        return f'human attestation replay cache unavailable: {type(exc).__name__}',token

def digest(obj):return object_digest(obj)

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create');c.add_argument('--case-id',required=True);c.add_argument('--actor-id',required=True);c.add_argument('--verdict',required=True,choices=['CONFIRMED','REJECTED']);c.add_argument('--head-sha',required=True);c.add_argument('--cycle-digest',required=True);c.add_argument('--evidence-digest',required=True);c.add_argument('--output',required=True);c.add_argument('--key-env',default='MAESTRO_HUMAN_DECISION_KEY');c.add_argument('--key-id',default='external-human-authority')
    v=sub.add_parser('validate');v.add_argument('--attestation',required=True);v.add_argument('--case-id',required=True);v.add_argument('--actor-id',required=True);v.add_argument('--verdict',required=True,choices=['CONFIRMED','REJECTED']);v.add_argument('--head-sha',required=True);v.add_argument('--cycle-digest',required=True);v.add_argument('--evidence-digest',required=True);v.add_argument('--key-env',default='MAESTRO_HUMAN_DECISION_KEY')
    ns=ap.parse_args();key=os.environ.get(ns.key_env)
    if not key:raise SystemExit(f'missing {ns.key_env}')
    if ns.cmd=='create':
        write_json(ns.output,create(ns.case_id,ns.actor_id,ns.verdict,ns.head_sha,key,ns.cycle_digest,ns.evidence_digest,ns.key_id));print(ns.output)
    else:
        obj=json.loads(Path(ns.attestation).read_text());errs=validate(obj,case_id=ns.case_id,actor_id=ns.actor_id,verdict=ns.verdict,head_sha=ns.head_sha,cycle_digest=ns.cycle_digest,evidence_digest=ns.evidence_digest,key=key)
        if errs:print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
        print('VALID')
if __name__=='__main__':main()
