from __future__ import annotations
import argparse,json,shutil,sys,os
from jsonschema import Draft202012Validator
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import write_json
from validate_case_record import semantic_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import canonical_anchor_path
from queue_policy import choose_queue
from case_ledger import default_anchor_path


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
    if any(x in {'random_audit_l1_selected','random_audit_l2_selected'} for x in labels):reasons.append('RANDOM_AUDIT')
    return sorted(set(reasons or ['RANDOM_AUDIT']))


def _copy_new(src,dst):
    d=Path(dst)
    if d.exists():raise SystemExit(f'immutable routing target already exists: {d}')
    d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,d);return d


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--evidence',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor');ap.add_argument('--rsi');ap.add_argument('--root',default=str(ROOT));ap.add_argument('--l1-ref',required=True);ap.add_argument('--l2-ref');ap.add_argument('--spec-ref');ap.add_argument('--standards-ref',action='append',default=[]);ap.add_argument('--test-ref',action='append',default=[]);ns=ap.parse_args()
    case=json.loads(Path(ns.case).read_text());schema=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
    if not __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', case.get('case_id','')): raise SystemExit('unsafe case_id')
    anchor=Path(ns.anchor) if ns.anchor else default_anchor_path(ns.ledger);errs=[e.message for e in Draft202012Validator(schema).iter_errors(case)] + semantic_errors(case);hmac_key=os.environ.get('MAESTRO_LEDGER_HMAC_KEY');errs+=bundle_errors(case,ns.ledger,anchor,False,hmac_key)
    if errs:raise SystemExit('invalid case bundle: '+'; '.join(errs))
    evidence=json.loads(Path(ns.evidence).read_text());
    if evidence.get('output_digest')!=case['sensor']['evidence_digest']:raise SystemExit('case/evidence digest mismatch')
    rsi=json.loads(Path(ns.rsi).read_text()) if ns.rsi else None;reasons=reasons_for(case,rsi);q=choose_queue(reasons,case.get('labels'),rsi,case.get('failure_families'));root=Path(ns.root)
    cb=root/'case-bank'/case['case_id']
    if cb.exists() and any(cb.iterdir()):raise SystemExit(f'immutable case-bank target already exists: {cb}')
    cb.mkdir(parents=True,exist_ok=True)
    _copy_new(ns.case,cb/'case-record.json');_copy_new(ns.evidence,cb/'textdiff-evidence.json');_copy_new(ns.ledger,cb/'case-events.jsonl');_copy_new(anchor,cb/'case-events.anchor.json')
    if ns.rsi:_copy_new(ns.rsi,cb/'rsi-evaluation.json')
    _copy_new(ns.l1_ref,cb/'l1-review.json')
    if ns.l2_ref:_copy_new(ns.l2_ref,cb/'l2-review.json')
    trail={r['level']:r for r in case.get('review_trail',[])};l1_digest=(trail.get('L1') or {}).get('result_digest');l2_digest=(trail.get('L2') or {}).get('result_digest')
    if not l1_digest:raise SystemExit('adversarial packet requires L1 result digest')
    standards=[str(Path(x).resolve()) for x in ns.standards_ref]
    tests=[str(Path(x).resolve()) for x in ns.test_ref]
    for x in standards+tests:
        if not Path(x).is_file():raise SystemExit(f'trusted packet ref missing: {x}')
    spec=str(Path(ns.spec_ref).resolve()) if ns.spec_ref else None
    if spec and not Path(spec).is_file():raise SystemExit(f'spec ref missing: {spec}')
    packet={'schema_version':'2.4','case_id':case['case_id'],'binding':case['binding'],'queue':q,'escalation_reasons':reasons,
      'refs':{'textdiff_evidence':str((cb/'textdiff-evidence.json').resolve()),'deterministic_policy':str((ROOT/'policy').resolve()),'l1_review':str((cb/'l1-review.json').resolve()),'l2_review':str((cb/'l2-review.json').resolve()) if ns.l2_ref else None,'trusted_standards':standards,'spec_ref':spec,'test_results':tests},
      'digests':{'textdiff_evidence':case['sensor']['evidence_digest'],'l1_review':l1_digest,'l2_review':l2_digest},
      'known_failure_families':case.get('failure_families',[]),'exact_question':'Independently adjudicate the lower-layer reviews, identify the wrong layer or standard gap, and do not inherit their conclusions.','requested_output':['final_verdict','wrong_layer','failure_family_class','standard_gap','regression_fixture_recommendation']}
    ps=json.loads((ROOT/'schemas/adversarial-packet.schema.json').read_text());pe=[e.message for e in Draft202012Validator(ps).iter_errors(packet)]
    if pe:raise SystemExit('invalid packet: '+'; '.join(pe))
    qdir=root/'adversarial_queue'/q;qdir.mkdir(parents=True,exist_ok=True);target=qdir/f'{case["case_id"]}.json'
    if target.exists():raise SystemExit(f'immutable queue packet already exists: {target}')
    write_json(target,packet);print(target)
if __name__=='__main__':main()
