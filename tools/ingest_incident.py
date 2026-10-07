from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import write_json
from validate_case_record import semantic_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import append_event,canonical_anchor_path
SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor');ap.add_argument('--ledger-hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');ap.add_argument('--incident-ref',required=True);ap.add_argument('--kind',choices=['incident','regression'],default='incident');ap.add_argument('--failure-family');ns=ap.parse_args();p=Path(ns.case);ledger=Path(ns.ledger);anchor=Path(ns.anchor) if ns.anchor else canonical_anchor_path(ledger);key=os.environ.get(ns.ledger_hmac_key_env);case=json.loads(p.read_text());errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(case)]+semantic_errors(case)+bundle_errors(case,ledger,anchor,False,key)
    if errs:raise SystemExit('invalid anchored case: '+'; '.join(errs))
    if not case.get('outcome',{}).get('merged'):raise SystemExit('post-merge incident requires merged=true')
    updated=json.loads(json.dumps(case));updated['outcome']['post_merge_status']=ns.kind;updated['outcome']['incident_ref']=ns.incident_ref;labels=set(updated.get('labels',[]));labels.add('post_merge_incident');labels.add('adversarial_reopen_required');updated['labels']=sorted(labels)
    if ns.failure_family:fam=set(updated.get('failure_families',[]));fam.add(ns.failure_family);updated['failure_families']=sorted(fam)
    errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(updated)]+semantic_errors(updated)
    if errs:raise SystemExit('updated case invalid: '+'; '.join(errs))
    tmp=p.with_suffix(p.suffix+'.pending');write_json(tmp,updated);append_event(ledger,case['case_id'],'INCIDENT_RECORDED',{'incident_ref':ns.incident_ref,'kind':ns.kind,'failure_family':ns.failure_family,'adversarial_reopen_required':True},anchor_path=anchor,hmac_key=key,key_id=ns.ledger_hmac_key_env if key else None);os.replace(tmp,p);print(p)
if __name__=='__main__':main()
