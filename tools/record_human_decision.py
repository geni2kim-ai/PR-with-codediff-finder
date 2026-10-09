from __future__ import annotations
import argparse,hashlib,hmac,json,os,subprocess,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import canonical_bytes,object_digest,sha256_bytes,write_json
from validate_case_record import semantic_errors as case_semantic_errors
from validate_review_cycle import semantic_errors as cycle_semantic_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import append_event,default_anchor_path,load_events,validate_events,validate_anchor,case_bundle_lock
from human_decision_attestation import validate as validate_human_attestation,digest as human_attestation_digest,consume_nonce as consume_human_nonce

CASE_SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
CYCLE_SCHEMA=json.loads((ROOT/'schemas/review-cycle.schema.json').read_text())
ZERO='0'*64

def git_head(repo):
    cp=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if cp.returncode:raise RuntimeError(cp.stderr[-1000:])
    return cp.stdout.strip()

def _validate_cycle(c):
    return [x.message for x in Draft202012Validator(CYCLE_SCHEMA).iter_errors(c)]+cycle_semantic_errors(c)

def _validate_case(c):
    return [x.message for x in Draft202012Validator(CASE_SCHEMA).iter_errors(c)]+case_semantic_errors(c)

def _latest_close(events):
    rows=[x for x in events if x.get('event_type')=='CYCLE_CLOSED']
    return rows[-1] if rows else None

def _matching_event(events,event_type,predicate):
    return next((x for x in events if x.get('event_type')==event_type and predicate(x.get('payload') or {})),None)

def _atomic_json(path,obj):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.replace')
    write_json(tmp,obj);os.replace(tmp,path)

def _transaction_hmac(tx,key):
    if not key:return None
    core={k:v for k,v in tx.items() if k!='transaction_hmac'}
    return hmac.new(key.encode('utf-8'),canonical_bytes(core),hashlib.sha256).hexdigest()

def _finish_transaction(tx_path,case_path,cycle_path,ledger,anchor,repo,att_path,ledger_key,human_key,ledger_key_id,replay_dir):
    tx=json.loads(Path(tx_path).read_text())
    if tx.get('transaction_digest')!=object_digest({k:v for k,v in tx.items() if k!='transaction_hmac'},'transaction_digest'):raise SystemExit('human transaction digest mismatch')
    if not human_key:raise SystemExit('human transaction HMAC key unavailable')
    mac=tx.get('transaction_hmac')
    if not mac or not hmac.compare_digest(mac,_transaction_hmac(tx,human_key)):raise SystemExit('human transaction HMAC mismatch')
    req=tx['request'];head=git_head(repo)
    expected_transaction_id=sha256_bytes(canonical_bytes({'case_id':req.get('case_id'),'review_id':req.get('review_id'),'attestation_digest':req.get('attestation_digest'),'source_cycle_digest':req.get('source_cycle_digest')}))
    if req.get('transaction_id')!=expected_transaction_id:raise SystemExit('human transaction id mismatch')
    if head!=req['head_sha']:raise SystemExit('repository HEAD changed since human transaction; recovery refused')
    att=tx['attestation']
    ae=validate_human_attestation(att,case_id=req['case_id'],actor_id=req['node_id'],verdict=req['verdict'],head_sha=head,cycle_digest=req['source_cycle_digest'],evidence_digest=req['evidence_digest'],key=human_key,enforce_freshness=False)
    if ae:raise SystemExit('invalid human decision attestation during recovery: '+'; '.join(ae))
    if human_attestation_digest(att)!=req['attestation_digest']:raise SystemExit('human transaction attestation digest mismatch')
    replay_error,_=consume_human_nonce(att,replay_dir,req['transaction_id'])
    if replay_error:raise SystemExit(replay_error)
    updated_case=tx['updated_case'];updated_cycle=tx['updated_cycle']
    ce=_validate_case(updated_case)+_validate_cycle(updated_cycle)
    if ce:raise SystemExit('human transaction state invalid: '+'; '.join(ce))
    if updated_case.get('case_id')!=req['case_id'] or updated_case.get('binding',{}).get('head_sha')!=head:raise SystemExit('human transaction case binding mismatch')
    expected_state='HUMAN_CONFIRMED' if req['verdict']=='CONFIRMED' else 'HUMAN_REJECTED'
    expected_gate='success' if req['verdict']=='CONFIRMED' else 'failure'
    if updated_cycle.get('state')!=expected_state or updated_cycle.get('gate_conclusion')!=expected_gate or updated_cycle.get('achieved_level')!='HUMAN':
        raise SystemExit('human transaction terminal state mismatch')

    events=load_events(ledger)
    errs=validate_events(events,req['case_id'])+validate_anchor(ledger,anchor,events,req['case_id'],ledger_key,require_hmac=(updated_cycle.get('execution_mode')=='ENFORCED'))
    if errs:raise SystemExit('invalid ledger during human transaction recovery: '+'; '.join(errs))

    hp=tx['human_event_payload'];cp=tx['close_event_payload']
    human=_matching_event(events,'HUMAN_DECISION',lambda p:p.get('review_id')==req['review_id'])
    if human:
        if human.get('payload')!=hp:raise SystemExit('conflicting HUMAN_DECISION already exists for review_id')
    else:
        append_event(ledger,req['case_id'],'HUMAN_DECISION',hp,anchor_path=anchor,hmac_key=ledger_key,key_id=ledger_key_id if ledger_key else None,event_instance_id='human:'+req['transaction_id'])
        events=load_events(ledger)

    close=_matching_event(events,'CYCLE_CLOSED',lambda p:p.get('cycle_digest')==updated_cycle['cycle_digest'])
    if close:
        if close.get('payload')!=cp:raise SystemExit('conflicting terminal CYCLE_CLOSED event')
    else:
        append_event(ledger,req['case_id'],'CYCLE_CLOSED',cp,anchor_path=anchor,hmac_key=ledger_key,key_id=ledger_key_id if ledger_key else None,event_instance_id='human-close:'+req['transaction_id'])

    _atomic_json(case_path,updated_case)
    _atomic_json(cycle_path,updated_cycle)
    _atomic_json(att_path,att)
    Path(tx_path).unlink(missing_ok=True)
    return updated_cycle

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--case',required=True);ap.add_argument('--cycle',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor')
    ap.add_argument('--repo',required=True);ap.add_argument('--attestation',required=True)
    ap.add_argument('--review-id',required=True);ap.add_argument('--node-id',required=True);ap.add_argument('--verdict',required=True,choices=['CONFIRMED','REJECTED'])
    ap.add_argument('--source-review-id');ap.add_argument('--note',default='')
    ap.add_argument('--ledger-hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');ap.add_argument('--human-key-env',default='MAESTRO_HUMAN_DECISION_KEY');ap.add_argument('--human-replay-dir')
    ns=ap.parse_args()

    case_path=Path(ns.case);cycle_path=Path(ns.cycle);ledger=Path(ns.ledger)
    anchor=Path(ns.anchor) if ns.anchor else default_anchor_path(ledger)
    tx_path=cycle_path.parent/'human-decision-transaction.json'
    persisted_att=cycle_path.parent/'human-decision-attestation.json'
    ledger_key=os.environ.get(ns.ledger_hmac_key_env);human_key=os.environ.get(ns.human_key_env)
    supplied_att=json.loads(Path(ns.attestation).read_text());supplied_digest=human_attestation_digest(supplied_att)
    configured_replay=os.environ.get('MAESTRO_HUMAN_DECISION_REPLAY_DIR')
    if not configured_replay:raise SystemExit('trusted shared human replay cache required: set MAESTRO_HUMAN_DECISION_REPLAY_DIR')
    replay_dir=Path(configured_replay).resolve()
    if ns.human_replay_dir and Path(ns.human_replay_dir).resolve()!=replay_dir:
        raise SystemExit('--human-replay-dir must match trusted MAESTRO_HUMAN_DECISION_REPLAY_DIR')
    case_bundle_dir=cycle_path.parent.resolve()
    if replay_dir==case_bundle_dir or case_bundle_dir in replay_dir.parents:
        raise SystemExit('human replay cache must be outside the mutable case bundle')

    with case_bundle_lock(case_path):
        if tx_path.exists():
            tx=json.loads(tx_path.read_text())
            req=tx.get('request',{})
            expected={'review_id':ns.review_id,'node_id':ns.node_id,'verdict':ns.verdict,'attestation_digest':supplied_digest}
            for k,v in expected.items():
                if req.get(k)!=v:raise SystemExit(f'pending human transaction does not match request: {k}')
            _finish_transaction(tx_path,case_path,cycle_path,ledger,anchor,ns.repo,persisted_att,ledger_key,human_key,ns.ledger_hmac_key_env,replay_dir)
            print(cycle_path);return
    
        case=json.loads(case_path.read_text());cycle=json.loads(cycle_path.read_text())
        errs=_validate_case(case)+_validate_cycle(cycle)
        if errs:raise SystemExit('invalid case/cycle: '+'; '.join(errs))
        if cycle.get('state')!='HUMAN_REQUIRED' or cycle.get('required_level')!='HUMAN':
            raise SystemExit('human decision requires HUMAN_REQUIRED cycle')
        if case.get('case_id')!=cycle.get('case_id') or case.get('binding',{}).get('head_sha')!=cycle.get('binding',{}).get('head_sha'):
            raise SystemExit('case/cycle binding mismatch')
    
        events=load_events(ledger)
        errs=validate_events(events,case['case_id'])+validate_anchor(ledger,anchor,events,case['case_id'],ledger_key,require_hmac=(cycle.get('execution_mode')=='ENFORCED'))
        errs+=bundle_errors(case,ledger,anchor,cycle.get('execution_mode')=='ENFORCED',ledger_key)
        if errs:raise SystemExit('invalid anchored case bundle: '+'; '.join(errs))
        close=_latest_close(events)
        if not close or close.get('payload',{}).get('cycle_digest')!=cycle.get('cycle_digest'):
            raise SystemExit('current cycle is not bound to latest CYCLE_CLOSED ledger event')
    
        head=git_head(ns.repo)
        if head!=case['binding']['head_sha']:raise SystemExit('repository HEAD changed since review; human decision refused')
        ae=validate_human_attestation(supplied_att,case_id=case['case_id'],actor_id=ns.node_id,verdict=ns.verdict,head_sha=head,cycle_digest=cycle['cycle_digest'],evidence_digest=case['sensor']['evidence_digest'],key=human_key)
        if ae:raise SystemExit('invalid human decision attestation: '+'; '.join(ae))
    
        trail=case.get('review_trail',[]);parent=ns.source_review_id or (trail[-1]['review_id'] if trail else None);last=trail[-1] if trail else None
        result_payload={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'model':None,'verdict':ns.verdict,'confidence':'not_applicable','reviewed_head_sha':head,'evidence_digest':case['sensor']['evidence_digest'],'note':ns.note,'attestation_digest':supplied_digest}
        row={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'model':None,'verdict':ns.verdict,'confidence':'not_applicable','result_digest':object_digest(result_payload),'reviewed_head_sha':head,'evidence_digest':case['sensor']['evidence_digest'],'input_digest':sha256_bytes(canonical_bytes(result_payload)),'prompt_digest':ZERO,'skill_digest':ZERO,'policy_digest':(last or {}).get('policy_digest',ZERO),'standards_digest':(last or {}).get('standards_digest',ZERO),'worker_command_digest':ZERO,'independent_context':True,'requested_level':'HUMAN','achieved_level':'HUMAN','timestamp':supplied_att.get('issued_at'),'finding_families':[]}
        updated_case=json.loads(json.dumps(case));updated_case['review_trail'].append(row)
        ce=_validate_case(updated_case)
        if ce:raise SystemExit('updated case invalid: '+'; '.join(ce))
    
        updated_cycle=json.loads(json.dumps(cycle));updated_cycle['achieved_level']='HUMAN';updated_cycle['current_head_verified']=True;updated_cycle['ledger_anchor_verified']=True
        updated_cycle['state']='HUMAN_CONFIRMED' if ns.verdict=='CONFIRMED' else 'HUMAN_REJECTED'
        updated_cycle['gate_conclusion']='success' if ns.verdict=='CONFIRMED' else 'failure'
        updated_cycle['cycle_digest']='';updated_cycle['cycle_digest']=object_digest(updated_cycle,'cycle_digest')
        ce=_validate_cycle(updated_cycle)
        if ce:raise SystemExit('updated cycle invalid: '+'; '.join(ce))
    
        human_event={'review_id':ns.review_id,'actor_id':ns.node_id,'verdict':ns.verdict,'head_sha':head,'source_cycle_digest':cycle['cycle_digest'],'evidence_digest':case['sensor']['evidence_digest'],'result_digest':row['result_digest'],'note_digest':sha256_bytes(ns.note.encode()),'attestation_digest':supplied_digest}
        close_event={'state':updated_cycle['state'],'cycle_digest':updated_cycle['cycle_digest'],'gate_conclusion':updated_cycle['gate_conclusion'],'human_review_id':ns.review_id,'human_attestation_digest':supplied_digest}
        transaction_id=sha256_bytes(canonical_bytes({'case_id':case['case_id'],'review_id':ns.review_id,'attestation_digest':supplied_digest,'source_cycle_digest':cycle['cycle_digest']}))
        tx={'schema_version':'2.7','request':{'case_id':case['case_id'],'review_id':ns.review_id,'node_id':ns.node_id,'verdict':ns.verdict,'head_sha':head,'attestation_digest':supplied_digest,'source_cycle_digest':cycle['cycle_digest'],'evidence_digest':case['sensor']['evidence_digest'],'transaction_id':transaction_id},'attestation':supplied_att,'updated_case':updated_case,'updated_cycle':updated_cycle,'human_event_payload':human_event,'close_event_payload':close_event,'transaction_digest':''}
        tx['transaction_digest']=object_digest(tx,'transaction_digest');tx['transaction_hmac']=_transaction_hmac(tx,human_key)
        _atomic_json(tx_path,tx)
        _finish_transaction(tx_path,case_path,cycle_path,ledger,anchor,ns.repo,persisted_att,ledger_key,human_key,ns.ledger_hmac_key_env,replay_dir)
        print(cycle_path)
    
if __name__=='__main__':main()
