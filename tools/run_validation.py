from __future__ import annotations
import argparse, json, os, re, signal, subprocess, sys, tempfile
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from validate_textdiff_evidence import semantic_errors as evidence_errors
from validate_case_record import semantic_errors as case_errors
from validate_case_bundle import errors as bundle_errors
from validate_review_result import semantic_errors as review_errors
from validate_rsi_evaluation import semantic_errors as rsi_errors
from validate_reviewer_task import validate as task_errors
from validate_stage_result import validate as stage_errors
from validate_review_cycle import semantic_errors as cycle_errors
from case_ledger import load_events,validate_events,validate_anchor
from validate_adjudication import semantic_errors as adjudication_errors
from validate_standard_candidate import semantic_errors as standard_errors

# v2.6 discovers test modules from tests/test_*.py so a newly added test file cannot
# silently disappear from the canonical validation run. The v2.3 module remains split
# into individual methods because those subprocess-heavy scenarios benefit from hard
# process isolation.
V23_SPLIT=[
 'tests.test_v23_orchestration.V23OrchestrationTests.test_low_risk_l1_pass_completes',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_auth_path_runs_independent_l2_then_requires_adversarial',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_l1_l2_disagreement_requires_adversarial',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_governance_path_needs_human_after_adversarial',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_head_change_during_review_becomes_stale',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_shadow_check_preview_is_forced_neutral',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_enforced_mode_rejects_unattested_isolation',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_unsafe_reviewer_output_is_rejected',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_stale_head_cancels_without_review',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_ledger_detects_tamper',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_outcome_incident_and_calibration',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_standard_candidate_requires_human_codeowner_approval',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_blocked_latest_stage_sets_blocked_state',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_effective_routing_policy_digest_is_bound',
 'tests.test_v23_orchestration.V23OrchestrationTests.test_stage_risk_escalation_reason_is_preserved',
]
def validation_modules():
    return [f'tests.{p.stem}' for p in sorted((ROOT/'tests').glob('test_*.py'))]

def validation_groups():
    mods=validation_modules()
    return [m for m in mods if m!='tests.test_v23_orchestration']+V23_SPLIT

def _enumerate_test_ids(names):
    # Import tests only in a disposable child process. Some test modules import
    # multiprocessing; importing them in this long-lived validation parent can
    # perturb later process creation on POSIX.
    script=r'''import json,sys,unittest
def flat(s):
    out=[]
    for x in s:
        if isinstance(x,unittest.TestSuite):out.extend(flat(x))
        else:out.append(x.id())
    return out
loader=unittest.TestLoader();out=[]
for name in json.loads(sys.argv[1]):out.extend(flat(loader.loadTestsFromName(name)))
print(json.dumps(out))
'''
    cp=subprocess.run([sys.executable,'-c',script,json.dumps(names)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    if cp.returncode:raise SystemExit('test enumeration failed: '+cp.stderr[-2000:])
    return json.loads(cp.stdout)

def validation_coverage_errors():
    mods=validation_modules();groups=validation_groups();all_ids=set(_enumerate_test_ids(mods));covered=set(_enumerate_test_ids(groups))
    missing=sorted(all_ids-covered);extra=sorted(covered-all_ids);e=[]
    if missing:e.append('validation groups omit tests: '+', '.join(missing))
    if extra:e.append('validation groups reference unknown tests: '+', '.join(extra))
    return e

def schema_errors(schema_rel,obj):
    schema=json.loads((ROOT/schema_rel).read_text());return [x.message for x in Draft202012Validator(schema).iter_errors(obj)]
def load(rel):return json.loads((ROOT/rel).read_text())
def assert_clean(label,errs):
    if errs:raise SystemExit(label+': '+'; '.join(errs))
    print(label+': PASS')
def _run_group(group, timeout):
    with tempfile.TemporaryDirectory(prefix='harness-test-') as td:
        op=Path(td)/'stdout';ep=Path(td)/'stderr'
        with op.open('wb') as of,ep.open('wb') as ef:
            proc=subprocess.Popen([sys.executable,'-m','unittest','-q',group],cwd=ROOT,stdout=of,stderr=ef,start_new_session=(os.name!='nt'))
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name!='nt':
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                else:proc.kill()
                proc.wait(timeout=5)
                err=ep.read_text(encoding='utf-8',errors='replace') if ep.exists() else ''
                return False,0,f'timeout after {timeout}s\n{err[-4000:]}'
            finally:
                # A test may exit while a descendant remains alive in its process
                # group.  Clean the whole group even on PASS so one test cannot
                # perturb later validation groups.
                if os.name!='nt':
                    try: os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError: pass
        out=op.read_text(encoding='utf-8',errors='replace');err=ep.read_text(encoding='utf-8',errors='replace')
        if proc.returncode:return False,0,f'exit {proc.returncode}\n{out[-2000:]}\n{err[-4000:]}'
        m=re.search(r'Ran\s+(\d+)\s+tests?',out+'\n'+err)
        return True,int(m.group(1)) if m else 0,''

def run_harness_tests_isolated(timeout=120,jobs=1):
    coverage=validation_coverage_errors()
    if coverage:raise SystemExit('; '.join(coverage))
    # One isolated OS process per group; the parent never imports test modules.
    total=0;failures=[]
    for group in validation_groups():
        ok,count,detail=_run_group(group,timeout);total+=count
        if not ok:failures.append((group,detail))
    if failures:
        lines=['harness isolated test-group failures:']
        for group,detail in failures:lines.append(f'- {group}: {detail}')
        raise SystemExit('\n'.join(lines))
    print(f'harness isolated tests: {total} PASS (groups={len(validation_groups())}, sequential)')
    return total

def validate_examples():
    ev=load('examples/textdiff-evidence.valid.json');assert_clean('textdiff evidence',schema_errors('schemas/textdiff-evidence.schema.json',ev)+evidence_errors(ev,ROOT/'policy/protected-paths.yml'))
    case=load('examples/case-record.valid.json');assert_clean('case record',schema_errors('schemas/case-record.schema.json',case)+case_errors(case))
    rr=load('examples/review-result.valid.json');assert_clean('review result',schema_errors('schemas/review-result.schema.json',rr)+review_errors(rr))
    rsi=load('examples/rsi-evaluation.valid.json');assert_clean('rsi evaluation',schema_errors('schemas/rsi-evaluation.schema.json',rsi)+rsi_errors(rsi,ROOT/'policy/rsi-scoring.yml'))
    ex=ROOT/'examples/v24/cycle'
    tasks={}
    for level in ('l1','l2','adversarial'):
        task=load(f'examples/v24/cycle/{level}-task.json');tasks[level]=task;assert_clean(f'{level} task',task_errors(task))
        rp=ex/f'{level}-review.json'
        if rp.exists():res=json.loads(rp.read_text());assert_clean(f'{level} result',stage_errors(res,task))
    cyc=load('examples/v24/cycle/review-cycle.json');assert_clean('review cycle',schema_errors('schemas/review-cycle.schema.json',cyc)+cycle_errors(cyc))
    events=load_events(ex/'case-events.jsonl');assert_clean('case ledger chain',validate_events(events,'CASE-V24-EXAMPLE'));assert_clean('case ledger anchor',validate_anchor(ex/'case-events.jsonl',ex/'case-events.anchor.json',events,'CASE-V24-EXAMPLE'))
    ex_case=load('examples/v24/cycle/case-record.json');assert_clean('case bundle',bundle_errors(ex_case,ex/'case-events.jsonl',ex/'case-events.anchor.json'))
    packet=load('examples/v24/cycle/adversarial-packet.json');assert_clean('adversarial packet',schema_errors('schemas/adversarial-packet.schema.json',packet))
    adj=load('examples/v24/adjudication.valid.json');assert_clean('adjudication',schema_errors('schemas/adjudication.schema.json',adj)+adjudication_errors(adj))
    std=load('examples/v24/standard-candidate.valid.json');assert_clean('standard candidate',schema_errors('schemas/standard-candidate.schema.json',std)+standard_errors(std))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--full',action='store_true',help='run all harness tests plus vendored TextDiffChecker regressions');ap.add_argument('--test-timeout',type=int,default=120);ap.add_argument('--jobs',type=int,default=1,help='reserved for compatibility; v2.6 runs discovered isolated groups sequentially to avoid fork/thread deadlocks');ns=ap.parse_args()
    run_harness_tests_isolated(ns.test_timeout,ns.jobs)
    validate_examples()
    if ns.full:
        subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'vendor/TextDiffChecker_v1.4.6-harness.1/tests'),'-q'],cwd=ROOT,check=True,timeout=120)
        subprocess.run([sys.executable,str(ROOT/'fixtures/diff-false-exact/fixture.py')],cwd=ROOT,check=True,timeout=30)
        print('vendored TextDiffChecker regressions + DIFF-FALSE-EXACT fixture: PASS')
    print('ALL VALIDATIONS PASS'+(' (FULL)' if ns.full else ' (HARNESS+EXAMPLES)'))
if __name__=='__main__':main()
