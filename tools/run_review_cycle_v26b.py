from __future__ import annotations
import hashlib,hmac,json,sys
from pathlib import Path
import run_review_cycle as base
from common import object_digest,write_json
from case_ledger import append_event,default_anchor_path
from policy_engine import derive_required_level,derive_risk,classify_paths,load_yaml
from worker_runtime_v26 import run_worker

ROOT=Path(__file__).resolve().parents[1]
_legacy_audit=base.audit_sample

def _arg(argv,name,default=None):
    try:return argv[argv.index(name)+1]
    except (ValueError,IndexError):return default

def seeded_audit(percent,key=None,label='AUDIT'):
    if percent<=0:return False
    case_id=_arg(sys.argv[1:],'--case-id','')
    if key:
        value=int.from_bytes(hmac.new(key.encode(),f'{label}:{case_id}'.encode(),hashlib.sha256).digest()[:8],'big')/2**64
        return value < percent/100.0
    return _legacy_audit(percent,None,label)

def _cycle_dir(raw):
    p=Path(raw)
    if (p/'review-cycle.json').is_file():return p
    xs=sorted(x for x in p.glob('attempt-*') if (x/'review-cycle.json').is_file())
    return xs[-1] if xs else None

def enforce_human_floor(argv):
    out=_cycle_dir(_arg(argv,'--output-dir',''))
    if not out:return
    cp=out/'review-cycle.json';ep=out/'textdiff-evidence.json'
    if not cp.is_file() or not ep.is_file():return
    cycle=json.loads(cp.read_text());evidence=json.loads(ep.read_text())
    if cycle.get('state') in {'STALE','BLOCKED','HUMAN_CONFIRMED','HUMAN_REJECTED'}:return
    paths=[]
    for row in evidence.get('files',[]):
        if row.get('old_path'):paths.append(row['old_path'])
        if row.get('path'):paths.append(row['path'])
    hits=classify_paths(paths,load_yaml(ROOT/'policy/protected-paths.yml'))
    model={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
    for name in ('adversarial-review.json','l2-review.json','l1-review.json'):
        p=out/name
        if p.is_file():model=json.loads(p.read_text()).get('risk_signal',model);break
    risk=derive_risk(model,hits)
    if not risk['human_review_required']:return
    if cycle.get('required_level')=='HUMAN' and cycle.get('state')=='HUMAN_REQUIRED':return
    cycle['required_level']='HUMAN';cycle['state']='HUMAN_REQUIRED';cycle['gate_conclusion']='action_required'
    reasons=set(cycle.get('escalation_reasons',[]));reasons.update('HUMAN:'+x for x in risk.get('floor_reasons',[]))
    if risk.get('matrix_human_review_required'):reasons.add('HUMAN:risk_matrix')
    cycle['escalation_reasons']=sorted(reasons);cycle['cycle_digest']='';cycle['cycle_digest']=object_digest(cycle,'cycle_digest');write_json(cp,cycle)
    ledger=out/'case-events.jsonl'
    if ledger.is_file():
        append_event(ledger,cycle['case_id'],'CYCLE_CLOSED',{'state':'HUMAN_REQUIRED','cycle_digest':cycle['cycle_digest'],'gate_conclusion':'action_required'},anchor_path=default_anchor_path(ledger))

def main():
    argv=sys.argv[1:];rp=_arg(argv,'--routing-policy',str(ROOT/'policy/reviewer-routing.yml'))
    mode=str(load_yaml(rp).get('mode','shadow')).upper()
    if mode=='ENFORCED' and '--disable-random-audit' in argv:raise SystemExit('--disable-random-audit is forbidden in ENFORCED mode')
    base.derive_required_level=derive_required_level;base.audit_sample=seeded_audit;base.run_worker=run_worker
    result=base.main();enforce_human_floor(argv);return result

if __name__=='__main__':main()
