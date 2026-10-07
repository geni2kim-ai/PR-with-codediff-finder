from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import object_digest,write_json
from case_ledger import append_event
from validate_adjudication import semantic_errors as adj_semantic
ADJ=json.loads((ROOT/'schemas/adjudication.schema.json').read_text());STD=json.loads((ROOT/'schemas/standard-candidate.schema.json').read_text())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--adjudication',required=True);ap.add_argument('--output',required=True);ap.add_argument('--title',required=True);ap.add_argument('--rule',required=True);ap.add_argument('--detection',required=True);ap.add_argument('--severity',choices=['blocker','major','minor','nit'],default='major');ap.add_argument('--good-example-ref');ap.add_argument('--bad-example-ref');ap.add_argument('--expires-on');ap.add_argument('--machine-enforceable',action='store_true');ap.add_argument('--ledger');ns=ap.parse_args();a=json.loads(Path(ns.adjudication).read_text())
    errs=[x.message for x in Draft202012Validator(ADJ).iter_errors(a)]+adj_semantic(a)
    if errs:raise SystemExit('invalid adjudication: '+'; '.join(errs))
    if not a['standard_gap']:raise SystemExit('adjudication does not identify a standard gap')
    cid='STD-'+re.sub(r'[^A-Za-z0-9._-]+','-',a['case_id'])[:96]
    o={'schema_version':'2.4','candidate_id':cid,'source_case_id':a['case_id'],'status':'PROPOSED','rule':{'title':ns.title,'text':ns.rule,'rationale':a['standard_gap_reason'],'good_example_ref':ns.good_example_ref,'bad_example_ref':ns.bad_example_ref,'expires_on':ns.expires_on},'detection':{'method':ns.detection,'machine_enforceable':ns.machine_enforceable},'severity':ns.severity,'evidence_refs':a['evidence_refs'],'approval':{'required':['HUMAN','CODEOWNER'],'approved':False},'candidate_digest':''};o['candidate_digest']=object_digest(o,'candidate_digest')
    errs=[x.message for x in Draft202012Validator(STD).iter_errors(o)]
    if errs:raise SystemExit('generated invalid standard candidate: '+'; '.join(errs))
    write_json(ns.output,o)
    if ns.ledger:append_event(ns.ledger,a['case_id'],'STANDARD_CANDIDATE_PROPOSED',{'candidate_id':o['candidate_id'],'candidate_digest':o['candidate_digest']})
    print(ns.output)
if __name__=='__main__':main()
