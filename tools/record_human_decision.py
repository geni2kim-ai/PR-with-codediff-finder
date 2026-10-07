from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import canonical_bytes,object_digest,sha256_bytes,write_json
from validate_case_record import semantic_errors
from case_ledger import append_event
SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text());ZERO='0'*64

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--review-id',required=True);ap.add_argument('--node-id',default='human-owner');ap.add_argument('--verdict',required=True,choices=['CONFIRMED','REJECTED']);ap.add_argument('--source-review-id');ap.add_argument('--note',default='');ns=ap.parse_args();p=Path(ns.case);c=json.loads(p.read_text())
    errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(c)]+semantic_errors(c)
    if errs:raise SystemExit('invalid case: '+'; '.join(errs))
    trail=c.get('review_trail',[]);parent=ns.source_review_id or (trail[-1]['review_id'] if trail else None);last=trail[-1] if trail else None
    payload={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'model':None,'verdict':ns.verdict,'confidence':'not_applicable','reviewed_head_sha':c['binding']['head_sha'],'evidence_digest':c['sensor']['evidence_digest'],'note':ns.note}
    r={'review_id':ns.review_id,'parent_review_id':parent,'level':'HUMAN','node_id':ns.node_id,'model':None,'verdict':ns.verdict,'confidence':'not_applicable','result_digest':object_digest(payload),'reviewed_head_sha':c['binding']['head_sha'],'evidence_digest':c['sensor']['evidence_digest'],'input_digest':sha256_bytes(canonical_bytes(payload)),'prompt_digest':ZERO,'skill_digest':ZERO,'policy_digest':(last or {}).get('policy_digest',ZERO),'standards_digest':(last or {}).get('standards_digest',ZERO),'independent_context':True,'requested_level':'HUMAN','achieved_level':'HUMAN','timestamp':None,'finding_families':[]}
    c['review_trail'].append(r);errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(c)]+semantic_errors(c)
    if errs:raise SystemExit('updated case invalid: '+'; '.join(errs))
    write_json(p,c);append_event(ns.ledger,c['case_id'],'HUMAN_DECISION',{'review_id':ns.review_id,'verdict':ns.verdict,'result_digest':r['result_digest'],'note_digest':sha256_bytes(ns.note.encode())});print(p)
if __name__=='__main__':main()
