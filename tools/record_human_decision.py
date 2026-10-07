from __future__ import annotations
import argparse,json,os,subprocess,sys,tempfile
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import canonical_bytes,object_digest,sha256_bytes
from validate_case_record import semantic_errors as case_errors
from validate_review_cycle import semantic_errors as cycle_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import append_event,default_anchor_path
CASE_SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
CYCLE_SCHEMA=json.loads((ROOT/'schemas/review-cycle.schema.json').read_text())
ZERO='0'*64

def atomic_json(path,obj):
    p=Path(path);fd,tmp=tempfile.mkstemp(prefix=p.name+'.',suffix='.tmp',dir=p.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        try:os.unlink(tmp)
        except FileNotFoundError:pass

def current_head(repo):
    cp=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if cp.returncode:raise SystemExit('cannot verify repository HEAD')
    return cp.stdout.strip()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--cycle',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor')
    ap.add_argument('--repo',required=True);ap.add_argument('--review-id',required=True);ap.add_argument('--node-id',default='human-owner');ap.add_argument('--actor',required=True)
    ap.add_argument('--verdict',required=True,choices=['CONFIRMED','REJECTED']);ap.add_argument('--source-review-id');ap.add_argument('--note',default='');ns=ap.parse_args()
    cp=Path(ns.case);yp=Path(ns.cycle);case=json.loads(cp.read_text());cycle=json.loads(yp.read_text())
    errs=[x.message for x in Draft202012Validator(CASE_SCHEMA).iter_errors(case)]+case_errors(case)
    errs += [x.message for x in Draft202012Validator(CYCLE_SCHEMA).iter_errors(cycle)]+cycle_errors(cycle)
    if errs:raise SystemExit('invalid input state: '+'; '.join(errs[:20]))
    if case['case_id']!=cycle['case_id'] or case['binding']['head_sha']!=cycle['binding']['head_sha']:raise SystemExit('case/cycle binding mismatch')
    if cycle['required_level']!='HUMAN' or cycle['state']!='HUMAN_REQUIRED':raise SystemExit('human decision requires HUMAN_REQUIRED cycle')
    head=current_head(ns.repo)
    if head!=case['binding']['head_sha']:raise SystemExit('current HEAD differs from reviewed head')
    if cycle.get('execution_mode')=='ENFORCED':raise SystemExit('ENFORCED human finalization requires an external identity-attestation adapter')
    anchor=Path(ns.anchor) if ns.anchor else default_anchor_path(ns.ledger)
    be=bundle_errors(case,ns.ledger,anchor,False,None)
    if be:raise SystemExit('invalid case bundle before human decision: '+'; '.join(be[:20]))

    trail=case.get('review_trail',[]);parent=ns.source_review_id or (trail[-1]['review_id'] if trail else None);last=trail[-1] if trail else None
    payload={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'actor':ns.actor,'verdict':ns.verdict,'confidence':'not_applicable','reviewed_head_sha':head,'evidence_digest':case['sensor']['evidence_digest'],'note':ns.note}
    row={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'model':None,'verdict':ns.verdict,'confidence':'not_applicable',
         'result_digest':object_digest(payload),'reviewed_head_sha':head,'evidence_digest':case['sensor']['evidence_digest'],'input_digest':sha256_bytes(canonical_bytes(payload)),
         'prompt_digest':ZERO,'skill_digest':ZERO,'policy_digest':(last or {}).get('policy_digest',ZERO),'standards_digest':(last or {}).get('standards_digest',ZERO),
         'independent_context':True,'requested_level':'HUMAN','achieved_level':'HUMAN','timestamp':None,'finding_families':[],'worker_command_digest':ZERO}
    new_case=json.loads(json.dumps(case));new_case['review_trail'].append(row)
    new_cycle=json.loads(json.dumps(cycle));new_cycle['achieved_level']='HUMAN';new_cycle['state']='HUMAN_CONFIRMED' if ns.verdict=='CONFIRMED' else 'HUMAN_REJECTED'
    new_cycle['gate_conclusion']='success' if ns.verdict=='CONFIRMED' else 'failure';new_cycle['current_head_verified']=True;new_cycle['ledger_anchor_verified']=True
    new_cycle['cycle_digest']='';new_cycle['cycle_digest']=object_digest(new_cycle,'cycle_digest')
    errs=[x.message for x in Draft202012Validator(CASE_SCHEMA).iter_errors(new_case)]+case_errors(new_case)
    errs += [x.message for x in Draft202012Validator(CYCLE_SCHEMA).iter_errors(new_cycle)]+cycle_errors(new_cycle)
    if errs:raise SystemExit('updated state invalid: '+'; '.join(errs[:20]))
    append_event(ns.ledger,case['case_id'],'HUMAN_DECISION',{'review_id':ns.review_id,'actor':ns.actor,'verdict':ns.verdict,'result_digest':row['result_digest'],'note_digest':sha256_bytes(ns.note.encode())},anchor_path=anchor)
    append_event(ns.ledger,case['case_id'],'CYCLE_CLOSED',{'state':new_cycle['state'],'cycle_digest':new_cycle['cycle_digest'],'gate_conclusion':new_cycle['gate_conclusion']},anchor_path=anchor)
    atomic_json(cp,new_case);atomic_json(yp,new_cycle);print(yp)
if __name__=='__main__':main()
