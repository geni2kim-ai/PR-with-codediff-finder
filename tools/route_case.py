from __future__ import annotations
import argparse,json,os,shutil,sys,tempfile
from jsonschema import Draft202012Validator
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import object_digest,sha256_file,write_json
from validate_case_record import semantic_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import default_anchor_path
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
    if any(x in {'random_audit_l1_selected','random_audit_l2_selected'} for x in labels):reasons.append('RANDOM_AUDIT')
    return sorted(set(reasons or ['RANDOM_AUDIT']))

def _load_file(path,label):
    p=Path(path).resolve()
    if not p.is_file():raise SystemExit(f'{label} missing: {p}')
    return p

def _review_digest(path,level,expected):
    p=_load_file(path,f'{level} review');obj=json.loads(p.read_text())
    if obj.get('level')!=level:raise SystemExit(f'{level} review level mismatch')
    if not expected or obj.get('result_digest')!=expected:raise SystemExit(f'{level} review digest mismatch')
    return p,obj

def _atomic_queue_write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        existing=json.loads(path.read_text())
        if existing!=obj:raise SystemExit(f'immutable queue packet conflict: {path}')
        return
    try:
        os.write(fd,data);os.fsync(fd)
    finally:os.close(fd)

def _recover_completed_case_bank(cb,root,schema):
    packet_path=cb/'adversarial-packet.json'
    if not packet_path.is_file():raise SystemExit(f'incomplete immutable case-bank target requires manual quarantine: {cb}')
    packet=json.loads(packet_path.read_text())
    errs=[e.message for e in Draft202012Validator(schema).iter_errors(packet)]
    if errs:raise SystemExit('stored adversarial packet invalid: '+'; '.join(errs))
    target=root/'adversarial_queue'/packet['queue']/f"{packet['case_id']}.json"
    _atomic_queue_write(target,packet)
    print(target)
    return True

def _copy(src,dst):
    dst=Path(dst);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)

def _frozen_files(srcs,stage_dir,final_dir,prefix):
    refs=[];digests=[]
    for i,src in enumerate(srcs,1):
        p=Path(src);suffix=p.suffix if p.suffix else '.dat';name=f'{prefix}-{i:03d}{suffix}'
        staged=stage_dir/name;_copy(p,staged)
        refs.append(str((final_dir/name).resolve()));digests.append(sha256_file(staged))
    return refs,digests

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--case',required=True);ap.add_argument('--evidence',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor')
    ap.add_argument('--rsi');ap.add_argument('--root',default=str(ROOT));ap.add_argument('--l1-ref',required=True);ap.add_argument('--l2-ref')
    ap.add_argument('--spec-ref');ap.add_argument('--standards-ref',action='append',default=[]);ap.add_argument('--test-ref',action='append',default=[])
    ns=ap.parse_args()

    root=Path(ns.root).resolve();schema=json.loads((ROOT/'schemas/adversarial-packet.schema.json').read_text())
    case=json.loads(Path(ns.case).read_text());case_schema=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
    if not __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',case.get('case_id','')):raise SystemExit('unsafe case_id')
    cb=root/'case-bank'/case['case_id']
    if cb.exists():
        _recover_completed_case_bank(cb,root,schema);return

    # Validate all mutable inputs before creating any immutable destination.
    anchor=Path(ns.anchor) if ns.anchor else default_anchor_path(ns.ledger)
    errs=[e.message for e in Draft202012Validator(case_schema).iter_errors(case)]+semantic_errors(case)
    hmac_key=os.environ.get('MAESTRO_LEDGER_HMAC_KEY');errs+=bundle_errors(case,ns.ledger,anchor,False,hmac_key)
    if errs:raise SystemExit('invalid case bundle: '+'; '.join(errs))
    evidence_path=_load_file(ns.evidence,'evidence');evidence=json.loads(evidence_path.read_text())
    if evidence.get('output_digest')!=case['sensor']['evidence_digest']:raise SystemExit('case/evidence digest mismatch')
    rsi_path=_load_file(ns.rsi,'RSI') if ns.rsi else None;rsi=json.loads(rsi_path.read_text()) if rsi_path else None
    trail={r['level']:r for r in case.get('review_trail',[])}
    l1_digest=(trail.get('L1') or {}).get('result_digest');l2_digest=(trail.get('L2') or {}).get('result_digest')
    l1_path,_=_review_digest(ns.l1_ref,'L1',l1_digest)
    l2_path=None
    if ns.l2_ref:l2_path,_=_review_digest(ns.l2_ref,'L2',l2_digest)
    elif l2_digest:raise SystemExit('case contains L2 review but --l2-ref was not supplied')
    standards=[_load_file(x,'standard ref') for x in ns.standards_ref]
    tests=[_load_file(x,'test ref') for x in ns.test_ref]
    spec=_load_file(ns.spec_ref,'spec ref') if ns.spec_ref else None
    policy_files=sorted((ROOT/'policy').glob('*.yml'))
    if not policy_files:raise SystemExit('deterministic policy files unavailable')

    reasons=reasons_for(case,rsi);q=choose_queue(reasons,case.get('labels'),rsi,case.get('failure_families'))
    bank_parent=cb.parent;bank_parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=f'.{case["case_id"]}.stage-',dir=bank_parent))
    try:
        _copy(ns.case,stage/'case-record.json');_copy(evidence_path,stage/'textdiff-evidence.json');_copy(ns.ledger,stage/'case-events.jsonl');_copy(anchor,stage/'case-events.anchor.json')
        if rsi_path:_copy(rsi_path,stage/'rsi-evaluation.json')
        _copy(l1_path,stage/'l1-review.json')
        if l2_path:_copy(l2_path,stage/'l2-review.json')

        trusted_stage=stage/'trusted';trusted_final=cb/'trusted'
        policy_stage=trusted_stage/'policy';policy_final=trusted_final/'policy';policy_stage.mkdir(parents=True,exist_ok=True)
        policy_index={'schema_version':'2.6','files':[]}
        for p in policy_files:
            dst=policy_stage/p.name;_copy(p,dst);policy_index['files'].append({'name':p.name,'sha256':sha256_file(dst)})
        write_json(trusted_stage/'policy-index.json',policy_index)
        policy_index_digest=sha256_file(trusted_stage/'policy-index.json')

        standard_refs,standard_digests=_frozen_files(standards,trusted_stage/'standards',trusted_final/'standards','standard')
        test_refs,test_digests=_frozen_files(tests,trusted_stage/'tests',trusted_final/'tests','test')
        spec_ref=None;spec_digest=None
        if spec:
            suffix=spec.suffix if spec.suffix else '.dat';staged=trusted_stage/('spec'+suffix);_copy(spec,staged)
            spec_ref=str((trusted_final/staged.name).resolve());spec_digest=sha256_file(staged)

        packet={'schema_version':'2.4','case_id':case['case_id'],'binding':case['binding'],'queue':q,'escalation_reasons':reasons,
          'refs':{'textdiff_evidence':str((cb/'textdiff-evidence.json').resolve()),'deterministic_policy':str((trusted_final/'policy-index.json').resolve()),'l1_review':str((cb/'l1-review.json').resolve()),'l2_review':str((cb/'l2-review.json').resolve()) if l2_path else None,'trusted_standards':standard_refs,'spec_ref':spec_ref,'test_results':test_refs},
          'digests':{'textdiff_evidence':case['sensor']['evidence_digest'],'deterministic_policy':policy_index_digest,'l1_review':l1_digest,'l2_review':l2_digest,'trusted_standards':standard_digests,'spec_ref':spec_digest,'test_results':test_digests},
          'known_failure_families':case.get('failure_families',[]),'exact_question':'Independently adjudicate the lower-layer reviews, identify the wrong layer or standard gap, and do not inherit their conclusions.','requested_output':['final_verdict','wrong_layer','failure_family_class','standard_gap','regression_fixture_recommendation']}
        pe=[e.message for e in Draft202012Validator(schema).iter_errors(packet)]
        if pe:raise SystemExit('invalid packet: '+'; '.join(pe))
        write_json(stage/'adversarial-packet.json',packet)
        os.replace(stage,cb)
        stage=None
    finally:
        if stage is not None and stage.exists():shutil.rmtree(stage,ignore_errors=True)

    target=root/'adversarial_queue'/q/f'{case["case_id"]}.json'
    packet=json.loads((cb/'adversarial-packet.json').read_text());_atomic_queue_write(target,packet);print(target)

if __name__=='__main__':main()
