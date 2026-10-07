from __future__ import annotations
import json, sys
from pathlib import Path
from jsonschema import Draft202012Validator
from policy_engine import load_yaml, classify_paths, derive_risk, derive_required_level, gate_conclusion

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/review-result.schema.json').read_text(encoding='utf-8'))
PROTECTED=load_yaml(ROOT/'policy/protected-paths.yml')
LEVELS=['L1','L2','ADVERSARIAL','HUMAN']
ACHIEVED=['SENSOR','L1','L2','ADVERSARIAL','HUMAN']

def semantic_errors(result, changed_paths=None, signals=None):
    errors=[]; changed_paths=changed_paths or []; signals=dict(signals or {})
    ident=result['identity']
    if ident['reviewed_head_sha'] != ident['current_head_sha'] and result['analysis_status'] not in {'STALE','ABANDONED'}:
        errors.append('head mismatch requires STALE/ABANDONED')
    counts={k:0 for k in ('blocker','major','minor','nit')}
    for f in result['findings']: counts[f['severity']]+=1
    if counts != result['summary']['finding_counts']: errors.append('finding_counts do not match findings')
    if result['analysis_status']=='PASS' and (counts['blocker'] or counts['major']): errors.append('PASS cannot contain blocker/major')
    required_checks=[c for c in result['deterministic_checks'] if c['status'] not in {'passed','not_required'}]
    if result['analysis_status']=='PASS' and required_checks: errors.append('PASS cannot have failed/unknown deterministic checks')
    os=result['output_safety']
    if os['external_urls_present'] or os['markdown_images_present'] or os['mentions_present'] or not os['secret_scan_passed'] or not os['sanitized']:
        errors.append('unsafe review output flags')
    spec=result.get('spec_ref')
    if spec and spec.get('modified_after_pr_open') and (spec.get('modified_by_pr_author') or not spec.get('post_open_change_explained')):
        signals['spec_changed_after_open']=True
    sensor=result.get('sensor_context') or {}
    if not sensor.get('trusted_for_gate', False): signals['sensor_runtime_untrusted']=True
    if sensor.get('quality_class')=='APPROXIMATE': signals['sensor_approximate']=True
    if sensor.get('low_confidence_encoding_paths'): signals['encoding_low_confidence']=True
    if sensor.get('failed_invariants'): signals['sensor_failed_invariant']=True
    rh=result['risk']['harness']; ma=result['risk']['model_assessment']
    protected_high=bool(rh.get('adversarial_floor_path_hits') or rh.get('human_floor_path_hits') or rh.get('governance_path_hits'))
    if sensor.get('quality_class')=='HEURISTIC' and (protected_high or ma.get('security_surface') in {'HIGH','CRITICAL'}): signals['sensor_heuristic_high_risk']=True
    if (not sensor.get('trusted_for_gate', False)) and protected_high: signals['sensor_runtime_untrusted_on_protected']=True
    if changed_paths:
        hits=classify_paths(changed_paths,PROTECTED)
        expected=derive_risk(result['risk']['model_assessment'],hits)
        for k in expected:
            if result['risk']['harness'][k] != expected[k]: errors.append(f'harness risk mismatch: {k}')
        req,_=derive_required_level(result['risk']['model_assessment'],hits,signals)
        if LEVELS.index(result['authority']['required_level']) < LEVELS.index(req): errors.append(f'required_level below harness-derived floor {req}')
    # Sensor-derived authority floors apply even when changed_paths are not separately supplied.
    sensor_floor='L1'
    if signals.get('sensor_runtime_untrusted') or signals.get('sensor_approximate') or signals.get('encoding_low_confidence'): sensor_floor='L2'
    if signals.get('sensor_failed_invariant') or signals.get('sensor_heuristic_high_risk') or signals.get('sensor_runtime_untrusted_on_protected'): sensor_floor='ADVERSARIAL'
    if LEVELS.index(result['authority']['required_level']) < LEVELS.index(sensor_floor): errors.append(f'required_level below sensor-derived floor {sensor_floor}')
    # State/authority consistency independent of path availability.
    req=result['authority']['required_level']; got=result['authority']['achieved_level']
    if ACHIEVED.index(got) < ACHIEVED.index(req):
        if req=='ADVERSARIAL' and result['review_state']!='ADV_REQUIRED': errors.append('unreached ADVERSARIAL requires ADV_REQUIRED state')
        if req=='HUMAN' and result['review_state'] not in {'HUMAN_REQUIRED','ADV_REQUIRED'}: errors.append('unreached HUMAN requires HUMAN_REQUIRED/ADV_REQUIRED state')
    if result['authority']['final_authority'] and ACHIEVED.index(got) < ACHIEVED.index(req): errors.append('final_authority cannot be true before required level is reached')
    return errors

def main():
    if len(sys.argv)<2: raise SystemExit('usage: validate_review_result.py RESULT.json [changed-paths.txt]')
    result=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    errs=[e.message for e in Draft202012Validator(SCHEMA).iter_errors(result)]
    paths=[]
    if len(sys.argv)>2: paths=[x.strip() for x in Path(sys.argv[2]).read_text(encoding='utf-8').splitlines() if x.strip()]
    errs += semantic_errors(result,paths)
    if errs:
        print('INVALID')
        for e in errs: print('-',e)
        raise SystemExit(1)
    print('VALID')
    print('gate_conclusion='+gate_conclusion(result))
if __name__=='__main__': main()
