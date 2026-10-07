from __future__ import annotations
import argparse,json,os,subprocess,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import canonical_bytes,object_digest,sha256_bytes,write_json
from validate_case_record import semantic_errors as case_semantic_errors
from validate_review_cycle import semantic_errors as cycle_semantic_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import append_event,canonical_anchor_path,load_events,validate_events,validate_anchor
from human_decision_attestation import validate as validate_human_attestation,digest as human_attestation_digest
CASE_SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text());CYCLE_SCHEMA=json.loads((ROOT/'schemas/review-cycle.schema.json').read_text());ZERO='0'*64
def git_head(repo):
    cp=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if cp.returncode:raise RuntimeError(cp.stderr[-1000:])
    return cp.stdout.strip()
def _validate_cycle(c):return [x.message for x in Draft202012Validator(CYCLE_SCHEMA).iter_errors(c)]+cycle_semantic_errors(c)
def _latest_close(events):
    rows=[x for x in events if x.get('event_type')=='CYCLE_CLOSED'];return rows[-1] if rows else None
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--cycle',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor');ap.add_argument('--repo',required=True);ap.add_argument('--attestation',required=True);ap.add_argument('--review-id',required=True);ap.add_argument('--node-id',required=True);ap.add_argument('--verdict',required=True,choices=['CONFIRMED','REJECTED']);ap.add_argument('--source-review-id');ap.add_argument('--note',default='');ap.add_argument('--ledger-hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');ap.add_argument('--human-key-env',default='MAESTRO_HUMAN_DECISION_KEY');ns=ap.parse_args()
    p=Path(ns.case);cp=Path(ns.cycle);ledger=Path(ns.ledger);anchor=Path(ns.anchor) if ns.anchor else canonical_anchor_path(ledger);case=json.loads(p.read_text());cycle=json.loads(cp.read_text())
    errs=[x.message for x in Draft202012Validator(CASE_SCHEMA).iter_errors(case)]+case_semantic_errors(case)+_validate_cycle(cycle)
    if errs:raise SystemExit('invalid case/cycle: '+'; '.join(errs))
    if cycle.get('state')!='HUMAN_REQUIRED' or cycle.get('required_level')!='HUMAN':raise SystemExit('human decision requires HUMAN_REQUIRED cycle')
    if case.get('case_id')!=cycle.get('case_id') or case.get('binding',{}).get('head_sha')!=cycle.get('binding',{}).get('head_sha'):raise SystemExit('case/cycle binding mismatch')
    ledger_key=os.environ.get(ns.ledger_hmac_key_env);events=load_events(ledger);errs=validate_events(events,case['case_id'])+validate_anchor(ledger,anchor,events,case['case_id'],ledger_key,require_hmac=(cycle.get('execution_mode')=='ENFORCED'));errs+=bundle_errors(case,ledger,anchor,cycle.get('execution_mode')=='ENFORCED',ledger_key)
    if errs:raise SystemExit('invalid anchored case bundle: '+'; '.join(errs))
    close=_latest_close(events)
    if not close or close.get('payload',{}).get('cycle_digest')!=cycle.get('cycle_digest'):raise SystemExit('current cycle is not bound to latest CYCLE_CLOSED ledger event')
    head=git_head(ns.repo)
    if head!=case['binding']['head_sha']:raise SystemExit('repository HEAD changed since review; human decision refused')
    human_key=os.environ.get(ns.human_key_env);att=json.loads(Path(ns.attestation).read_text());ae=validate_human_attestation(att,case_id=case['case_id'],actor_id=ns.node_id,verdict=ns.verdict,head_sha=head,key=human_key)
    if ae:raise SystemExit('invalid human decision attestation: '+'; '.join(ae))
    trail=case.get('review_trail',[]);parent=ns.source_review_id or (trail[-1]['review_id'] if trail else None);last=trail[-1] if trail else None
    payload={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'model':None,'verdict':ns.verdict,'confidence':'not_applicable','reviewed_head_sha':head,'evidence_digest':case['sensor']['evidence_digest'],'note':ns.note,'attestation_digest':human_attestation_digest(att)}
    row={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'model':None,'verdict':ns.verdict,'confidence':'not_applicable','result_digest':object_digest(payload),'reviewed_head_sha':head,'evidence_digest':case['sensor']['evidence_digest'],'input_digest':sha256_bytes(canonical_bytes(payload)),'prompt_digest':ZERO,'skill_digest':ZERO,'policy_digest':(last or {}).get('policy_digest',ZERO),'standards_digest':(last or {}).get('standards_digest',ZERO),'worker_command_digest':ZERO,'independent_context':True,'requested_level':'HUMAN','achieved_level':'HUMAN','timestamp':att.get('issued_at'),'finding_families':[]}
    updated_case=json.loads(json.dumps(case));updated_case['review_trail'].append(row);ce=[x.message for x in Draft202012Validator(CASE_SCHEMA).iter_errors(updated_case)]+case_semantic_errors(updated_case)
    if ce:raise SystemExit('updated case invalid: '+'; '.join(ce))
    updated_cycle=json.loads(json.dumps(cycle));updated_cycle['achieved_level']='HUMAN';updated_cycle['current_head_verified']=True;updated_cycle['ledger_anchor_verified']=True;updated_cycle['state']='HUMAN_CONFIRMED' if ns.verdict=='CONFIRMED' else 'HUMAN_REJECTED';updated_cycle['gate_conclusion']='success' if ns.verdict=='CONFIRMED' else 'failure';updated_cycle['cycle_digest']='';updated_cycle['cycle_digest']=object_digest(updated_cycle,'cycle_digest');ce=_validate_cycle(updated_cycle)
    if ce:raise SystemExit('updated cycle invalid: '+'; '.join(ce))
    case_tmp=p.with_suffix(p.suffix+'.pending');cycle_tmp=cp.with_suffix(cp.suffix+'.pending');write_json(case_tmp,updated_case);write_json(cycle_tmp,updated_cycle)
    append_event(ledger,case['case_id'],'HUMAN_DECISION',{'review_id':ns.review_id,'verdict':ns.verdict,'result_digest':row['result_digest'],'note_digest':sha256_bytes(ns.note.encode()),'attestation_digest':human_attestation_digest(att)},anchor_path=anchor,hmac_key=ledger_key,key_id=ns.ledger_hmac_key_env if ledger_key else None)
    append_event(ledger,case['case_id'],'CYCLE_CLOSED',{'state':updated_cycle['state'],'cycle_digest':updated_cycle['cycle_digest'],'gate_conclusion':updated_cycle['gate_conclusion'],'human_review_id':ns.review_id},anchor_path=anchor,hmac_key=ledger_key,key_id=ns.ledger_hmac_key_env if ledger_key else None)
    os.replace(case_tmp,p);os.replace(cycle_tmp,cp);print(cp)
if __name__=='__main__':main()
