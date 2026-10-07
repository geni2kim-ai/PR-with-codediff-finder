from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from common import sha256_file,write_json
from policy_engine import load_yaml
from validate_rsi_evaluation import derive
from validate_textdiff_evidence import semantic_errors as evidence_errors
from validate_case_record import semantic_errors as case_errors
from case_ledger import append_event
EVAL_VERSION='2.4.0'

def inv_status(ev,id):
    for x in ev.get('invariants',[]):
        if x.get('id')==id:return x.get('status')
    return 'unknown'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--evidence',required=True);ap.add_argument('--case',required=True);ap.add_argument('--output',required=True);ap.add_argument('--oracle');ap.add_argument('--attempts',type=int,default=1);ap.add_argument('--reproduced',type=int,default=1);ap.add_argument('--family-occurrences',type=int,default=1);ap.add_argument('--policy',default=str(ROOT/'policy/rsi-scoring.yml'));ap.add_argument('--ledger');ns=ap.parse_args()
    ev=json.loads(Path(ns.evidence).read_text());case=json.loads(Path(ns.case).read_text());oracle=json.loads(Path(ns.oracle).read_text()) if ns.oracle else {}
    ee=evidence_errors(ev,ROOT/'policy/protected-paths.yml');ce=case_errors(case)
    if ee or ce: raise SystemExit('invalid input: '+'; '.join(ee+ce))
    if case['sensor']['evidence_digest'] != ev['output_digest']: raise SystemExit('case/evidence digest mismatch')
    if case['sensor']['semantic_digest'] != ev['semantic_digest']: raise SystemExit('case/evidence semantic digest mismatch')
    q=ev['summary']['quality_class'];tags=set()
    apply=inv_status(ev,'apply-opcodes-reconstruct-target');correctness=1.0 if apply=='passed' else (0.0 if apply=='failed' else 0.75)
    applicable=[f for f in ev['files'] if not (f['binary'] or f['submodule'] or f['symlink'])]
    analyzed=sum(f['status']=='ANALYZED' for f in applicable);coverage=1.0 if not applicable else analyzed/len(applicable)
    det=inv_status(ev,'repeat-determinism');stability={'passed':1.0,'failed':0.0,'unknown':0.75,'not_required':0.8}.get(det,0.75)
    ms=ev['performance']['elapsed_ms'];performance=1.0 if ms<=2000 else 0.8 if ms<=10000 else 0.5 if ms<=30000 else 0.2
    calibration={'PROVEN_EXACT':1.0,'DETERMINISTIC':0.98,'HEURISTIC':0.9,'APPROXIMATE':0.9,'NOT_APPLICABLE':0.8}[q]
    safety=1.0 if ev['trust']['runtime_safety']=='PASS' else 0.25
    if q=='HEURISTIC':tags.add('DIFF-HEURISTIC')
    if q=='APPROXIMATE':tags.add('DIFF-APPROXIMATE')
    if any(f['encoding']['confidence']=='LOW' for f in ev['files']):tags.add('ENCODING-UNCERTAIN')
    if ev['summary']['weakening_signals']:tags.add('CHECK-WEAKENING-SIGNAL')
    if any(x['status']=='failed' for x in ev['invariants']):tags.add('INVARIANT-FAILED')
    if not ev['tool']['regex_timeout_available']:tags.add('RESOURCE-UNBOUNDED')
    if oracle.get('false_exact'):
        tags.add('DIFF-FALSE-EXACT');correctness=min(correctness,float(oracle.get('correctness_score',0.45)));calibration=min(calibration,0.2)
    if oracle.get('correctness_score') is not None:correctness=min(correctness,float(oracle['correctness_score']))
    # Preserve externally adjudicated sensor failure families without treating reviewer-only families as sensor defects.
    for x in case.get('failure_families',[]):
        if x.startswith('DIFF-') or x.startswith('SENSOR-'):tags.add(x)
    levels={x['level'] for x in case.get('review_trail',[])};src=['invariant']+[x for x in ('L1','L2','ADVERSARIAL','HUMAN') if x in levels]
    if case.get('outcome',{}).get('author_response') not in {'no_response','not_applicable'}:src.append('AUTHOR_OUTCOME')
    if case.get('outcome',{}).get('post_merge_status') not in {'unknown','not_applicable'}:src.append('POST_MERGE')
    if oracle:src.append('oracle')
    out={'schema_version':'2.4','case_id':case['case_id'],'sensor_result_digest':ev['output_digest'],'evaluation_sources':src,
         'scores':{'correctness':round(correctness,4),'coverage':round(coverage,4),'stability':round(stability,4),'performance':round(performance,4),'calibration':round(calibration,4),'safety':round(safety,4)},
         'overall_score':0,'failure_tags':sorted(tags),'reproduction':{'attempts':ns.attempts,'reproduced':ns.reproduced},'family_occurrences':ns.family_occurrences,
         'promotion':{'case_bank':False,'adversarial_required':False,'improvement_candidate':False,'reason':'harness-derived'},
         'derived_by':{'evaluator_version':EVAL_VERSION,'policy_digest':sha256_file(ns.policy)}}
    cfg=load_yaml(ns.policy);overall,p=derive(out,cfg);out['overall_score']=overall;out['promotion'].update(p)
    write_json(ns.output,out)
    if ns.ledger:append_event(ns.ledger,case['case_id'],'RSI_EVALUATED',{'overall_score':out['overall_score'],'failure_tags':out['failure_tags'],'promotion':out['promotion'],'evaluation_digest':__import__('hashlib').sha256(Path(ns.output).read_bytes()).hexdigest()})
if __name__=='__main__':main()
