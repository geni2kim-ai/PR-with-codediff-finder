from __future__ import annotations
import argparse,json,shutil,sys,os
from jsonschema import Draft202012Validator
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import write_json
from validate_case_record import semantic_errors
from validate_case_bundle import errors as bundle_errors
from queue_policy import choose_queue

def reasons_for(case,rsi=None):
    labels=set(case.get('labels',[]));trail=case.get('review_trail',[]);reasons=[];by={}
    for r in trail:by.setdefault(r['level'],[]).append(r)
    l1=by.get('L1',[]);l2=by.get('L2',[])
    if l1 and l2 and l1[-1]['verdict']!=l2[-1]['verdict']:reasons.append('L1_L2_DISAGREEMENT')
    if any(r.get('confidence')=='low' for r in trail):reasons.append('LOW_CONFIDENCE')
    if 'novel_failure_family' in labels or (rsi and 'NOVEL-FAILURE-FAMILY' in rsi.get('failure_tags',[])):reasons.append('NOVEL_FAILURE_FAMILY')
    if 'governance' in labels:reasons.append('GOVERNANCE_CHANGE')
    if 'post_merge_incident' in labels or 'adversarial_reopen_required' in labels:reasons.append('POST_MERGE_INCIDENT')
    if rsi and rsi.get('promotion',{}).get('adversarial_required'):reasons.append('RSI_ADVERSARIAL_REQUIRED')
    if any(x in set(case.get('failure_families',[])) for x in {'SECURITY-CRITICAL','DATA-CORRUPTION'}):reasons.append('CRITICAL')
    if any(x.startswith('random_audit_') for x in labels):reasons.append('RANDOM_AUDIT')
    return sorted(set(reasons or ['RANDOM_AUDIT']))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--evidence',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor');ap.add_argument('--rsi');ap.add_argument('--root',default=str(ROOT));ap.add_argument('--l1-ref',required=True);ap.add_argument('--l2-ref');ap.add_argument('--spec-ref');ns=ap.parse_args()
    case=json.loads(Path(ns.case).read_text());schema=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
    if not __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', case.get('case_id','')): raise SystemExit('unsafe case_id')
    errs=[e.message for e in Draft202012Validator(schema).iter_errors(case)] + semantic_errors(case);anchor=ns.anchor or str(ns.ledger)+'.anchor.json';anchor_obj=json.loads(Path(anchor).read_text()) if Path(anchor).is_file() else {};hmac_key=os.environ.get('MAESTRO_LEDGER_HMAC_KEY');require_hmac=bool(anchor_obj.get('hmac_sha256'));errs+=bundle_errors(case,ns.ledger,anchor,require_hmac,hmac_key)
    if errs:raise SystemExit('invalid case bundle: '+'; '.join(errs))
    evidence=json.loads(Path(ns.evidence).read_text());
    if evidence.get('output_digest')!=case['sensor']['evidence_digest']:raise SystemExit('case/evidence digest mismatch')
    rsi=json.loads(Path(ns.rsi).read_text()) if ns.rsi else None;reasons=reasons_for(case,rsi);q=choose_queue(reasons,case.get('labels'),rsi,case.get('failure_families'));root=Path(ns.root)
    cb=root/'case-bank'/case['case_id'];cb.mkdir(parents=True,exist_ok=True)
    copied={}
    for label,src,name in [('case',ns.case,'case-record.json'),('evidence',ns.evidence,'textdiff-evidence.json'),('ledger',ns.ledger,'case-events.jsonl'),('anchor',anchor,'case-events.anchor.json')]:
        shutil.copy2(src,cb/name);copied[label]=cb/name
    if ns.rsi:shutil.copy2(ns.rsi,cb/'rsi-evaluation.json')
    if ns.l1_ref:shutil.copy2(ns.l1_ref,cb/'l1-review.json')
    if ns.l2_ref:shutil.copy2(ns.l2_ref,cb/'l2-review.json')
    trail={r['level']:r for r in case.get('review_trail',[])}
    l1_digest=(trail.get('L1') or {}).get('result_digest');l2_digest=(trail.get('L2') or {}).get('result_digest')
    if not l1_digest:raise SystemExit('adversarial packet requires L1 result digest')
    packet={'schema_version':'2.4','case_id':case['case_id'],'binding':case['binding'],'queue':q,'escalation_reasons':reasons,
      'refs':{'textdiff_evidence':str((cb/'textdiff-evidence.json').resolve()),'deterministic_policy':str((ROOT/'policy').resolve()),'l1_review':str((cb/'l1-review.json').resolve()) if ns.l1_ref else None,'l2_review':str((cb/'l2-review.json').resolve()) if ns.l2_ref else None,'trusted_standards':[],'spec_ref':str(Path(ns.spec_ref).resolve()) if ns.spec_ref else None,'test_results':[]},
      'digests':{'textdiff_evidence':case['sensor']['evidence_digest'],'l1_review':l1_digest,'l2_review':l2_digest},
      'known_failure_families':case.get('failure_families',[]),'exact_question':'Independently adjudicate the lower-layer reviews, identify the wrong layer or standard gap, and do not inherit their conclusions.','requested_output':['final_verdict','wrong_layer','failure_family_class','standard_gap','regression_fixture_recommendation']}
    ps=json.loads((ROOT/'schemas/adversarial-packet.schema.json').read_text());pe=[e.message for e in Draft202012Validator(ps).iter_errors(packet)]
    if pe:raise SystemExit('invalid packet: '+'; '.join(pe))
    qdir=root/'adversarial_queue'/q;qdir.mkdir(parents=True,exist_ok=True);write_json(qdir/f'{case["case_id"]}.json',packet);print(qdir/f'{case["case_id"]}.json')
if __name__=='__main__':main()
