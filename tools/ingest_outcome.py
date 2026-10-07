from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import write_json
from validate_case_record import semantic_errors
from case_ledger import append_event
SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text())

def valid(case):return [x.message for x in Draft202012Validator(SCHEMA).iter_errors(case)]+semantic_errors(case)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--author-response',required=True,choices=['fixed','rejected','accepted_risk','no_response','not_applicable']);ap.add_argument('--merged',required=True,choices=['true','false']);ap.add_argument('--merge-sha');ap.add_argument('--post-merge-status',default='unknown',choices=['clean','incident','regression','unknown','not_applicable']);ap.add_argument('--incident-ref');ns=ap.parse_args();p=Path(ns.case);case=json.loads(p.read_text());errs=valid(case)
    if errs:raise SystemExit('invalid case: '+'; '.join(errs))
    merged=ns.merged=='true'
    if merged and not ns.merge_sha:raise SystemExit('merge-sha required when merged=true')
    if not merged and ns.merge_sha:raise SystemExit('merge-sha forbidden when merged=false')
    if ns.post_merge_status in {'incident','regression'} and not ns.incident_ref:raise SystemExit('incident-ref required for incident/regression')
    case['outcome']={'author_response':ns.author_response,'merged':merged,'merge_sha':ns.merge_sha,'post_merge_status':ns.post_merge_status,'incident_ref':ns.incident_ref}
    errs=valid(case)
    if errs:raise SystemExit('updated case invalid: '+'; '.join(errs))
    write_json(p,case);append_event(ns.ledger,case['case_id'],'OUTCOME_RECORDED',case['outcome']);print(p)
if __name__=='__main__':main()
