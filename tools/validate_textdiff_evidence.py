from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from common import object_digest, sha256_file
from policy_engine import load_yaml,classify_paths
Q={"NOT_APPLICABLE":-1,"PROVEN_EXACT":0,"HEURISTIC":1,"APPROXIMATE":2}
HEURISTIC_EVENTS={"sequence_matcher","positional_low_hamming","banded_myers","patience_crosscheck","patience_split"}
APPROX_EVENTS={"coarse_positional","coarse_replace"}


def _git_errors(o,repo,expected_base=None):
    from textdiff_adapter import resolve_commit,merge_base,git_change_snapshot
    e=[];repo=Path(repo).resolve();b=o.get('binding',{})
    try:head=resolve_commit(repo,'HEAD')
    except Exception as exc:return [f'git HEAD unavailable: {type(exc).__name__}']
    if b.get('head_sha')!=head:e.append('evidence head_sha does not match repository HEAD')
    if expected_base:
        try:
            base_tip=resolve_commit(repo,expected_base);mb=merge_base(repo,base_tip,head)
            if b.get('base_ref_sha')!=base_tip:e.append('evidence base_ref_sha does not match trusted base ref')
            if b.get('base_sha')!=mb:e.append('evidence base_sha does not match merge-base(trusted base, HEAD)')
        except Exception as exc:e.append(f'trusted base verification failed: {type(exc).__name__}')
    try:actual=git_change_snapshot(repo,b.get('base_sha',''),b.get('head_sha',''))
    except Exception as exc:return e+[f'git evidence snapshot failed: {type(exc).__name__}']
    keys=('path','old_path','change_type','base_blob_sha','head_blob_sha','mode_before','mode_after')
    exp=[{k:r.get(k) for k in keys} for r in o.get('files',[])]
    act=[{k:r.get(k) for k in keys} for r in actual]
    if exp!=act:e.append('evidence file metadata does not match canonical git diff')
    return e


def semantic_errors(o,policy_path=None,repo=None,expected_base=None):
    e=[]
    if o.get('output_digest') != object_digest(o,'output_digest'):e.append('output_digest mismatch')
    semantic_view={k:v for k,v in o.items() if k not in {'performance','semantic_digest','output_digest'}}
    if o.get('semantic_digest') != object_digest(semantic_view):e.append('semantic_digest mismatch')
    files=o.get('files',[]);s=o.get('summary',{})
    sums={'files_changed':len(files),'a_lines':sum(x['lines']['a'] for x in files),'b_lines':sum(x['lines']['b'] for x in files),'hunk_count':sum(x['diff']['hunk_count'] for x in files),'changed_lines':sum(x['diff']['changed_lines'] for x in files)}
    for k,v in sums.items():
        if s.get(k)!=v:e.append(f'summary {k} mismatch: stored={s.get(k)} computed={v}')
    aq=[x['diff']['quality_class'] for x in files if x['status']=='ANALYZED'];q='NOT_APPLICABLE' if not aq else max(aq,key=lambda x:Q[x])
    if s.get('quality_class')!=q:e.append(f'summary quality_class mismatch: stored={s.get("quality_class")} computed={q}')
    agg=[]
    for f in files:agg.extend(f.get('weakening_signals',[]))
    def norm(x):return sorted((r.get('kind'),r.get('path'),r.get('evidence')) for r in x)
    if norm(s.get('weakening_signals',[]))!=norm(agg):e.append('summary weakening_signals mismatch')
    nontext=sorted({f['path'] for f in files if f.get('symlink') or f.get('submodule') or f.get('binary')})
    if sorted(s.get('nontext_sensitive_paths',[]))!=nontext:e.append('summary nontext_sensitive_paths mismatch')
    for f in files:
        d=f['diff'];path=f['path'];alg=set(d.get('algorithm_path',[]))
        if f['status']=='ANALYZED' and d['quality_class']=='NOT_APPLICABLE':e.append(f'{path}: analyzed file cannot be NOT_APPLICABLE')
        if f['status']!='ANALYZED' and d['quality_class']!='NOT_APPLICABLE':e.append(f'{path}: non-analyzed file must be NOT_APPLICABLE')
        if d.get('approx') and d['quality_class']!='APPROXIMATE':e.append(f'{path}: approx=true requires APPROXIMATE')
        if alg & APPROX_EVENTS and d['quality_class']!='APPROXIMATE':e.append(f'{path}: coarse path requires APPROXIMATE')
        if alg & HEURISTIC_EVENTS and d['quality_class']=='PROVEN_EXACT':e.append(f'{path}: heuristic path cannot be PROVEN_EXACT')
        if 'full_myers_exceeded' in alg and 'banded_myers' in alg and d['quality_class']=='PROVEN_EXACT':e.append(f'{path}: banded after full cap cannot be PROVEN_EXACT')
    inv=o.get('invariants',[]);failed=[x['id'] for x in inv if x['status']=='failed'];trust=o.get('trust',{});regex=o.get('tool',{}).get('regex_timeout_available')
    sensor_cfg=load_yaml(ROOT/'policy/sensor-policy.yml');tdcfg=sensor_cfg.get('textdiff',{});regex_required=bool(tdcfg.get('trusted_runtime_requires_regex_timeout',True));quality_allowed=s.get('quality_class') in set(tdcfg.get('accepted_quality_classes',[]))
    error_file=any(x['status'] in {'ERROR','TIMEOUT'} for x in files);coverage_gap=any(x['status'] in {'SKIPPED','BINARY'} for x in files)
    must_untrust=(regex_required and not regex) or (not quality_allowed) or bool(failed) or error_file or coverage_gap
    if must_untrust and trust.get('trusted_for_gate'):e.append('trusted_for_gate must be false when runtime/invariant/file coverage gap exists')
    if (regex_required and not regex) and trust.get('runtime_safety')!='FAIL':e.append('runtime_safety must FAIL without required regex timeout')
    pin=sensor_cfg.get('trusted_tool',{});tool=o.get('tool',{})
    actual={'checker_sha256':tool.get('checker_sha256'),'original_package_sha256':tool.get('package_sha256'),'vendor_requirements_sha256':tool.get('dependencies_sha256'),'harness_requirements_sha256':tool.get('harness_dependencies_sha256')}
    for k,v in pin.items():
        if actual.get(k)!=v:e.append(f'trusted tool pin mismatch: {k}')
    # The policy itself pins expected package bytes; additionally verify currently installed harness dependency declaration.
    if tool.get('harness_dependencies_sha256')!=sha256_file(ROOT/'requirements.txt'):e.append('harness dependency declaration hash mismatch')
    if policy_path:
        cfg=load_yaml(policy_path);paths=[]
        for x in files:
            if x.get('old_path'):paths.append(x['old_path'])
            paths.append(x['path'])
        hits=classify_paths(paths,cfg);expected=sorted(set(sum(hits.values(),[])))
        if sorted(s.get('protected_candidates',[]))!=expected:e.append('protected_candidates mismatch canonical policy')
    if o.get('binding',{}).get('comparison_mode')!='merge-base':e.append('comparison_mode must be merge-base')
    if repo:e.extend(_git_errors(o,repo,expected_base))
    return e


def main():
    ap=argparse.ArgumentParser();ap.add_argument('json');ap.add_argument('--policy',default=str(ROOT/'policy/protected-paths.yml'));ap.add_argument('--repo');ap.add_argument('--expected-base');ns=ap.parse_args()
    o=json.loads(Path(ns.json).read_text(encoding='utf-8'));schema=json.loads((ROOT/'schemas/textdiff-evidence.schema.json').read_text(encoding='utf-8'))
    se=list(Draft202012Validator(schema).iter_errors(o));ee=semantic_errors(o,ns.policy,ns.repo,ns.expected_base)
    if se or ee:
        for x in se:print('SCHEMA:',x.message)
        for x in ee:print('SEMANTIC:',x)
        raise SystemExit(1)
    print('PASS')
if __name__=='__main__':main()
