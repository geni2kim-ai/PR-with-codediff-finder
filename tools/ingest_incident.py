from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import write_json
from validate_case_record import semantic_errors
from case_ledger import append_event
SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--incident-ref',required=True);ap.add_argument('--kind',choices=['incident','regression'],default='incident');ap.add_argument('--failure-family');ns=ap.parse_args();p=Path(ns.case);case=json.loads(p.read_text())
    errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(case)]+semantic_errors(case)
    if errs:raise SystemExit('invalid case: '+'; '.join(errs))
    if not case.get('outcome',{}).get('merged'):raise SystemExit('post-merge incident requires merged=true')
    case['outcome']['post_merge_status']=ns.kind;case['outcome']['incident_ref']=ns.incident_ref
    labels=set(case.get('labels',[]));labels.add('post_merge_incident');labels.add('adversarial_reopen_required');case['labels']=sorted(labels)
    if ns.failure_family:
        fam=set(case.get('failure_families',[]));fam.add(ns.failure_family);case['failure_families']=sorted(fam)
    write_json(p,case);append_event(ns.ledger,case['case_id'],'INCIDENT_RECORDED',{'incident_ref':ns.incident_ref,'kind':ns.kind,'failure_family':ns.failure_family,'adversarial_reopen_required':True});print(p)
if __name__=='__main__':main()
