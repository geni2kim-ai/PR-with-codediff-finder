from __future__ import annotations
import argparse,json,os,shutil,sys,tempfile
from jsonschema import Draft202012Validator
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import named_files_digest,object_digest,sha256_file,write_json
from validate_case_record import semantic_errors
from validate_case_bundle import errors as bundle_errors
from validate_textdiff_evidence import semantic_errors as evidence_semantic_errors
from validate_stage_result import validate as validate_stage_result
from case_ledger import default_anchor_path
from queue_policy import choose_queue
def _trail_material_state(row):
    if row.get('verdict')=='BLOCKED':return 'BLOCKED'
    if 'material_finding_count' in row:
        return 'FINDINGS' if int(row.get('material_finding_count',0))>0 else 'PASS'
    return row.get('verdict')

def _trail_material_signature(row):
    state=_trail_material_state(row)
    if state!='FINDINGS':return (state,())
    signatures=row.get('material_finding_signatures')
    if isinstance(signatures,list) and signatures:
        return (state,('severity_keys',tuple(sorted(str(x) for x in signatures if x))))
    keys=row.get('material_finding_keys')
    if isinstance(keys,list) and keys:
        return (state,('keys',tuple(sorted(set(str(x) for x in keys if x))),int(row.get('material_finding_count',len(keys)))))
    return (state,None)

def _trail_material_agrees(a,b):
    sa=_trail_material_signature(a);sb=_trail_material_signature(b)
    if sa[1] is None or sb[1] is None:return sa[0]==sb[0]
    return sa==sb

def reasons_for(case,rsi=None):
    labels=set(case.get('labels',[]));trail=case.get('review_trail',[]);reasons=[];by={}
    for r in trail:by.setdefault(r['level'],[]).append(r)
    l1=by.get('L1',[]);l2=by.get('L2',[])
    if l1 and l2 and not _trail_material_agrees(l1[-1],l2[-1]):reasons.append('L1_L2_DISAGREEMENT')
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
def _effective_policy_digest(routing_policy,policy_dir=None):
    root=Path(policy_dir).resolve() if policy_dir else (ROOT/'policy').resolve();entries=[]
    for p in sorted(root.glob('*.yml')):
        if p.name!='reviewer-routing.yml':entries.append((f'policy/{p.name}',p))
    entries.append(('policy/reviewer-routing.effective.yml',Path(routing_policy).resolve()))
    return named_files_digest(entries)

def _frozen_cycle_policy(case_path,requested_routing=None):
    cycle_root=Path(case_path).resolve().parent;policy_dir=cycle_root/'effective-policy'
    if policy_dir.is_dir():
        frozen=_load_file(policy_dir/'reviewer-routing.yml','frozen routing policy')
        if requested_routing:
            requested=_load_file(requested_routing,'routing policy')
            if sha256_file(requested)!=sha256_file(frozen):
                raise SystemExit('routing policy override does not match frozen cycle policy')
        return policy_dir,frozen
    routing=_load_file(requested_routing,'routing policy') if requested_routing else _load_file(ROOT/'policy/reviewer-routing.yml','routing policy')
    return (ROOT/'policy').resolve(),routing

def _frozen_cycle_inputs(case_path,standards_refs,spec_ref,test_refs):
    cycle_root=Path(case_path).resolve().parent;trusted=cycle_root/'trusted-inputs'
    frozen_standards=sorted((trusted/'standards').glob('*')) if (trusted/'standards').is_dir() else []
    frozen_tests=sorted((trusted/'tests').glob('*')) if (trusted/'tests').is_dir() else []
    frozen_specs=sorted((trusted/'spec').glob('*')) if (trusted/'spec').is_dir() else []
    if len(frozen_specs)>1:raise SystemExit('multiple frozen spec files found')
    standards=frozen_standards if frozen_standards else [_load_file(x,'standard ref') for x in standards_refs]
    tests=frozen_tests if frozen_tests else [_load_file(x,'test ref') for x in test_refs]
    spec=frozen_specs[0] if frozen_specs else (_load_file(spec_ref,'spec ref') if spec_ref else None)
    return standards,spec,tests,bool(frozen_standards)
def _review_digest(path,level,expected,evidence_digest,head_sha,expected_policy_digest):
    p=_load_file(path,f'{level} review');obj=json.loads(p.read_text());errs=validate_stage_result(obj)
    if errs:raise SystemExit(f'{level} review invalid: '+'; '.join(errs))
    actual=object_digest(obj,'result_digest')
    if obj.get('level')!=level:raise SystemExit(f'{level} review level mismatch')
    if not expected or actual!=expected or obj.get('result_digest')!=actual:raise SystemExit(f'{level} review digest mismatch')
    if obj.get('evidence_digest')!=evidence_digest:raise SystemExit(f'{level} review evidence digest mismatch')
    if obj.get('binding',{}).get('reviewed_head_sha')!=head_sha:raise SystemExit(f'{level} review head binding mismatch')
    if obj.get('reviewer',{}).get('policy_digest')!=expected_policy_digest:raise SystemExit(f'{level} review effective policy digest mismatch')
    return p,obj
def _atomic_queue_write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);data=(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        if json.loads(path.read_text())!=obj:raise SystemExit(f'immutable queue packet conflict: {path}')
        return
    try:os.write(fd,data);os.fsync(fd)
    finally:os.close(fd)
def _case_bank_ref(cb,raw,label):
    if not raw:raise SystemExit(f'case-bank {label} ref missing')
    root=Path(cb).resolve();p=Path(raw).resolve()
    if root!=p and root not in p.parents:raise SystemExit(f'case-bank {label} ref escapes immutable bundle')
    if not p.is_file():raise SystemExit(f'case-bank {label} file missing')
    return p

def _validate_case_bank_refs(cb,packet,expected_case):
    refs=packet.get('refs',{});digests=packet.get('digests',{})
    evidence_path=_case_bank_ref(cb,refs.get('textdiff_evidence'),'evidence')
    try:evidence=json.loads(evidence_path.read_text())
    except Exception as exc:raise SystemExit(f'case-bank evidence unreadable: {type(exc).__name__}')
    expected_evidence=digests.get('textdiff_evidence')
    if evidence.get('output_digest')!=expected_evidence or object_digest(evidence,'output_digest')!=expected_evidence:
        raise SystemExit('case-bank evidence digest mismatch')
    if expected_evidence!=expected_case.get('sensor',{}).get('evidence_digest'):
        raise SystemExit('case-bank evidence/case digest mismatch')

    policy_path=_case_bank_ref(cb,refs.get('deterministic_policy'),'deterministic policy')
    if sha256_file(policy_path)!=digests.get('deterministic_policy'):raise SystemExit('case-bank deterministic policy digest mismatch')

    for level,ref_key,digest_key in (('L1','l1_review','l1_review'),('L2','l2_review','l2_review')):
        raw=refs.get(ref_key);expected=digests.get(digest_key)
        if raw is None and expected is None:continue
        review_path=_case_bank_ref(cb,raw,f'{level} review')
        try:review=json.loads(review_path.read_text())
        except Exception as exc:raise SystemExit(f'case-bank {level} review unreadable: {type(exc).__name__}')
        errs=validate_stage_result(review)
        if errs:raise SystemExit(f'case-bank {level} review invalid: '+'; '.join(errs))
        if review.get('result_digest')!=expected or object_digest(review,'result_digest')!=expected:
            raise SystemExit(f'case-bank {level} review digest mismatch')

    for ref_key,digest_key,label in (('trusted_standards','trusted_standards','standard'),('test_results','test_results','test result')):
        raw_refs=refs.get(ref_key) or [];expected=digests.get(digest_key) or []
        if len(raw_refs)!=len(expected):raise SystemExit(f'case-bank {label} ref/digest count mismatch')
        for i,(raw,digest_value) in enumerate(zip(raw_refs,expected),1):
            p=_case_bank_ref(cb,raw,f'{label} {i}')
            if sha256_file(p)!=digest_value:raise SystemExit(f'case-bank {label} {i} digest mismatch')

    raw_spec=refs.get('spec_ref');spec_digest=digests.get('spec_ref')
    if raw_spec is None and spec_digest is not None:raise SystemExit('case-bank spec ref missing')
    if raw_spec is not None:
        p=_case_bank_ref(cb,raw_spec,'spec')
        if not spec_digest or sha256_file(p)!=spec_digest:raise SystemExit('case-bank spec digest mismatch')

    ledger=Path(cb)/'case-events.jsonl';anchor=Path(cb)/'case-events.anchor.json'
    bundle_errs=bundle_errors(expected_case,ledger,anchor,False,os.environ.get('MAESTRO_LEDGER_HMAC_KEY'))
    if bundle_errs:raise SystemExit('invalid recovered case-bank bundle: '+'; '.join(bundle_errs))

def _recover_completed_case_bank(cb,root,schema,expected_case):
    stored_case_path=cb/'case-record.json';packet_path=cb/'adversarial-packet.json'
    if not stored_case_path.is_file() or not packet_path.is_file():raise SystemExit(f'incomplete immutable case-bank target requires manual quarantine: {cb}')
    stored_case=json.loads(stored_case_path.read_text())
    if stored_case!=expected_case:raise SystemExit(f'immutable case-bank case mismatch for reused case_id: {expected_case.get("case_id")}')
    packet=json.loads(packet_path.read_text());errs=[e.message for e in Draft202012Validator(schema).iter_errors(packet)]
    if errs:raise SystemExit('stored adversarial packet invalid: '+'; '.join(errs))
    if packet.get('case_id')!=expected_case.get('case_id') or packet.get('binding')!=expected_case.get('binding'):
        raise SystemExit('stored adversarial packet binding does not match immutable case record')
    if packet.get('digests',{}).get('textdiff_evidence')!=expected_case.get('sensor',{}).get('evidence_digest'):
        raise SystemExit('stored adversarial packet evidence digest does not match immutable case record')
    _validate_case_bank_refs(cb,packet,expected_case)
    target=root/'adversarial_queue'/packet['queue']/f"{packet['case_id']}.json";_atomic_queue_write(target,packet);print(target);return True
def _copy(src,dst):
    dst=Path(dst);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def _frozen_files(srcs,stage_dir,final_dir,prefix):
    refs=[];digests=[]
    for i,src in enumerate(srcs,1):
        p=Path(src);suffix=p.suffix if p.suffix else '.dat';name=f'{prefix}-{i:03d}{suffix}';staged=stage_dir/name;_copy(p,staged);refs.append(str((final_dir/name).resolve()));digests.append(sha256_file(staged))
    return refs,digests
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--evidence',required=True);ap.add_argument('--ledger',required=True);ap.add_argument('--anchor');ap.add_argument('--rsi');ap.add_argument('--root',default=str(ROOT));ap.add_argument('--l1-ref',required=True);ap.add_argument('--l2-ref');ap.add_argument('--spec-ref');ap.add_argument('--standards-ref',action='append',default=[]);ap.add_argument('--test-ref',action='append',default=[]);ap.add_argument('--routing-policy');ns=ap.parse_args()
    root=Path(ns.root).resolve();schema=json.loads((ROOT/'schemas/adversarial-packet.schema.json').read_text());case_path=Path(ns.case).resolve();case=json.loads(case_path.read_text());case_schema=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
    if not __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',case.get('case_id','')):raise SystemExit('unsafe case_id')
    cb=root/'case-bank'/case['case_id']
    if cb.exists():_recover_completed_case_bank(cb,root,schema,case);return
    anchor=Path(ns.anchor) if ns.anchor else default_anchor_path(ns.ledger);errs=[e.message for e in Draft202012Validator(case_schema).iter_errors(case)]+semantic_errors(case);hmac_key=os.environ.get('MAESTRO_LEDGER_HMAC_KEY');errs+=bundle_errors(case,ns.ledger,anchor,False,hmac_key)
    if errs:raise SystemExit('invalid case bundle: '+'; '.join(errs))
    policy_dir,routing_path=_frozen_cycle_policy(case_path,ns.routing_policy)
    evidence_path=_load_file(ns.evidence,'evidence');evidence=json.loads(evidence_path.read_text());evidence_schema=json.loads((ROOT/'schemas/textdiff-evidence.schema.json').read_text());ee=[e.message for e in Draft202012Validator(evidence_schema).iter_errors(evidence)]+evidence_semantic_errors(evidence,policy_dir/'protected-paths.yml',verify_git=False,sensor_policy_path=policy_dir/'sensor-policy.yml')
    if ee:raise SystemExit('invalid evidence: '+'; '.join(ee))
    if evidence.get('output_digest')!=case['sensor']['evidence_digest']:raise SystemExit('case/evidence digest mismatch')
    for k in ('repository','base_sha','head_sha'):
        if evidence.get('binding',{}).get(k)!=case.get('binding',{}).get(k):raise SystemExit(f'case/evidence binding mismatch: {k}')
    effective_policy_digest=_effective_policy_digest(routing_path,policy_dir)
    rsi_path=_load_file(ns.rsi,'RSI') if ns.rsi else None;rsi=json.loads(rsi_path.read_text()) if rsi_path else None;trail={r['level']:r for r in case.get('review_trail',[])};l1_digest=(trail.get('L1') or {}).get('result_digest');l2_digest=(trail.get('L2') or {}).get('result_digest')
    for level in ('L1','L2'):
        if level in trail and trail[level].get('policy_digest')!=effective_policy_digest:raise SystemExit(f'{level} case trail effective policy digest mismatch')
    l1_path,_=_review_digest(ns.l1_ref,'L1',l1_digest,evidence['output_digest'],case['binding']['head_sha'],effective_policy_digest);l2_path=None
    if ns.l2_ref:l2_path,_=_review_digest(ns.l2_ref,'L2',l2_digest,evidence['output_digest'],case['binding']['head_sha'],effective_policy_digest)
    elif l2_digest:raise SystemExit('case contains L2 review but --l2-ref was not supplied')
    standards,spec,tests,standards_from_cycle=_frozen_cycle_inputs(case_path,ns.standards_ref,ns.spec_ref,ns.test_ref)
    if standards_from_cycle:
        expected_standards_digest=named_files_digest([(str(x).replace('\\','/'),Path(x).resolve()) for x in standards])
        for level in ('L1','L2'):
            if level in trail and trail[level].get('standards_digest')!=expected_standards_digest:raise SystemExit(f'{level} frozen standards digest mismatch')
    base_policies=[p for p in sorted(Path(policy_dir).glob('*.yml')) if p.name!='reviewer-routing.yml']
    reasons=reasons_for(case,rsi);q=choose_queue(reasons,case.get('labels'),rsi,case.get('failure_families'));bank_parent=cb.parent;bank_parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=f'.{case["case_id"]}.stage-',dir=bank_parent))
    try:
        _copy(ns.case,stage/'case-record.json');_copy(evidence_path,stage/'textdiff-evidence.json');_copy(ns.ledger,stage/'case-events.jsonl');_copy(anchor,stage/'case-events.anchor.json')
        if rsi_path:_copy(rsi_path,stage/'rsi-evaluation.json')
        _copy(l1_path,stage/'l1-review.json')
        if l2_path:_copy(l2_path,stage/'l2-review.json')
        trusted_stage=stage/'trusted';trusted_final=cb/'trusted';policy_stage=trusted_stage/'policy';policy_final=trusted_final/'policy';policy_stage.mkdir(parents=True,exist_ok=True);policy_index={'schema_version':'2.7','files':[]}
        for p in base_policies:
            dst=policy_stage/p.name;_copy(p,dst);policy_index['files'].append({'name':p.name,'sha256':sha256_file(dst)})
        routed=policy_stage/'reviewer-routing.yml';_copy(routing_path,routed);policy_index['files'].append({'name':'reviewer-routing.yml','sha256':sha256_file(routed)});policy_index['files'].sort(key=lambda x:x['name']);policy_index['reviewer_provenance_digest']=effective_policy_digest;write_json(trusted_stage/'policy-index.json',policy_index);policy_index_digest=sha256_file(trusted_stage/'policy-index.json')
        standard_refs,standard_digests=_frozen_files(standards,trusted_stage/'standards',trusted_final/'standards','standard');test_refs,test_digests=_frozen_files(tests,trusted_stage/'tests',trusted_final/'tests','test');spec_ref=None;spec_digest=None
        if spec:
            suffix=spec.suffix if spec.suffix else '.dat';staged=trusted_stage/('spec'+suffix);_copy(spec,staged);spec_ref=str((trusted_final/staged.name).resolve());spec_digest=sha256_file(staged)
        packet={'schema_version':'2.4','case_id':case['case_id'],'binding':case['binding'],'queue':q,'escalation_reasons':reasons,'refs':{'textdiff_evidence':str((cb/'textdiff-evidence.json').resolve()),'deterministic_policy':str((trusted_final/'policy-index.json').resolve()),'l1_review':str((cb/'l1-review.json').resolve()),'l2_review':str((cb/'l2-review.json').resolve()) if l2_path else None,'trusted_standards':standard_refs,'spec_ref':spec_ref,'test_results':test_refs},'digests':{'textdiff_evidence':case['sensor']['evidence_digest'],'deterministic_policy':policy_index_digest,'l1_review':l1_digest,'l2_review':l2_digest,'trusted_standards':standard_digests,'spec_ref':spec_digest,'test_results':test_digests},'known_failure_families':case.get('failure_families',[]),'exact_question':'Independently adjudicate the lower-layer reviews, identify the wrong layer or standard gap, and do not inherit their conclusions.','requested_output':['final_verdict','wrong_layer','failure_family_class','standard_gap','regression_fixture_recommendation']}
        pe=[e.message for e in Draft202012Validator(schema).iter_errors(packet)]
        if pe:raise SystemExit('invalid packet: '+'; '.join(pe))
        write_json(stage/'adversarial-packet.json',packet);os.replace(stage,cb);stage=None
    finally:
        if stage is not None and stage.exists():shutil.rmtree(stage,ignore_errors=True)
    target=root/'adversarial_queue'/q/f'{case["case_id"]}.json';packet=json.loads((cb/'adversarial-packet.json').read_text());_atomic_queue_write(target,packet);print(target)
if __name__=='__main__':main()
