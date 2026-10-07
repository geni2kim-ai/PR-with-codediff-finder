from __future__ import annotations
import hashlib,hmac,sys
from pathlib import Path
import run_review_cycle as base
from policy_engine import derive_required_level,load_yaml
from worker_runtime_v26 import run_worker

ROOT=Path(__file__).resolve().parents[1]

def seeded_audit(percent,key=None,label='AUDIT'):
    if percent<=0:return False
    argv=sys.argv[1:]
    try:i=argv.index('--case-id');case_id=argv[i+1]
    except (ValueError,IndexError):case_id=''
    if key:
        n=int.from_bytes(hmac.new(key.encode(),f'{label}:{case_id}'.encode(),hashlib.sha256).digest()[:8],'big')/2**64
        return n < percent/100.0
    return base.audit_sample(percent,None,label)

def main():
    argv=sys.argv[1:]
    try:i=argv.index('--routing-policy');rp=argv[i+1]
    except (ValueError,IndexError):rp=str(ROOT/'policy/reviewer-routing.yml')
    cfg=load_yaml(rp);mode=str(cfg.get('mode','shadow')).upper()
    if mode=='ENFORCED' and '--disable-random-audit' in argv:
        raise SystemExit('--disable-random-audit is forbidden in ENFORCED mode')
    base.derive_required_level=derive_required_level
    base.audit_sample=seeded_audit
    base.run_worker=run_worker
    return base.main()

if __name__=='__main__':main()
