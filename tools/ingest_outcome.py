from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import object_digest,write_json
from validate_case_record import semantic_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import append_event,canonical_anchor_path,load_events,validate_events,validate_anchor,case_bundle_lock
SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
def valid(case):return [x.message for x in Draft202012Validator(SCHEMA).iter_errors(case)]+semantic_errors(case)
def _atomic_json(path,obj):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.replace');write_json(tmp,obj);os.replace(tmp,path)
def _finish(tx_path,p,ledger,anchor,key,key_id):
    with case_bundle_lock(p):
        tx=json.loads(Path(tx_path).read_text())
        if tx.get('transaction_digest')!=object_digest(tx,'transaction_digest'):raise SystemExit('outcome transaction digest mismatch')
        if tx.get('event_type')!='OUTCOME_RECORDED':raise SystemExit('outcome transaction type mismatch')
        updated=tx.get('updated_case');errs=valid(updated)
        if errs:raise SystemExit('outcome transaction case invalid: '+'; '.join(errs))
        events=load_events(ledger);errs=validate_events(events,updated['case_id'])+validate_anchor(ledger,anchor,events,updated['case_id'],key,False)
        if errs:raise SystemExit('outcome transaction ledger invalid: '+'; '.join(errs))
        payload=tx['event_payload']
        if not any(e.get('event_type')=='OUTCOME_RECORDED' and e.get('payload')==payload for e in events):append_event(ledger,updated['case_id'],'OUTCOME_RECORDED',payload,anchor_path=anchor,hmac_key=key,key_id=key_id if key else None)
        _atomic_json(p,updated);errs=bundle_errors(updated,ledger,anchor,False,key)
        if errs:raise SystemExit('recovered outcome bundle invalid: '+'; '.join(errs))
        Path(tx_path).unlink(missing_ok=True)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor');ap.add_argument('--ledger-hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');ap.add_argument('--author-response',required=True,choices=['fixed','rejected','accepted_risk','no_response','not_applicable']);ap.add_argument('--merged',required=True,choices=['true','false']);ap.add_argument('--merge-sha');ap.add_argument('--post-merge-status',default='unknown',choices=['clean','incident','regression','unknown','not_applicable']);ap.add_argument('--incident-ref');ns=ap.parse_args();p=Path(ns.case);ledger=Path(ns.ledger);anchor=Path(ns.anchor) if ns.anchor else canonical_anchor_path(ledger);key=os.environ.get(ns.ledger_hmac_key_env);merged=ns.merged=='true'
    if merged and not ns.merge_sha:raise SystemExit('merge-sha required when merged=true')
    if not merged and ns.merge_sha:raise SystemExit('merge-sha forbidden when merged=false')
    if ns.post_merge_status in {'incident','regression'} and not ns.incident_ref:raise SystemExit('incident-ref required for incident/regression')
    request={'author_response':ns.author_response,'merged':merged,'merge_sha':ns.merge_sha,'post_merge_status':ns.post_merge_status,'incident_ref':ns.incident_ref};tx_path=p.parent/'outcome-transaction.json'
    if tx_path.exists():
        tx=json.loads(tx_path.read_text())
        if tx.get('request')!=request:raise SystemExit('pending outcome transaction does not match request')
        _finish(tx_path,p,ledger,anchor,key,ns.ledger_hmac_key_env);print(p);return
    case=json.loads(p.read_text());errs=valid(case)+bundle_errors(case,ledger,anchor,False,key)
    if errs:raise SystemExit('invalid anchored case: '+'; '.join(errs))
    updated=json.loads(json.dumps(case));updated['outcome']=request;errs=valid(updated)
    if errs:raise SystemExit('updated case invalid: '+'; '.join(errs))
    tx={'schema_version':'2.7','request':request,'event_type':'OUTCOME_RECORDED','event_payload':updated['outcome'],'updated_case':updated,'transaction_digest':''};tx['transaction_digest']=object_digest(tx,'transaction_digest');_atomic_json(tx_path,tx);_finish(tx_path,p,ledger,anchor,key,ns.ledger_hmac_key_env);print(p)
if __name__=='__main__':main()
