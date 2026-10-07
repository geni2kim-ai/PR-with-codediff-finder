from __future__ import annotations
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'

def run(cmd,**kw):
    kw.setdefault('timeout',20)
    return subprocess.run(cmd,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
def cmdjson(mode): return json.dumps([sys.executable,str(TOOLS/'mock_reviewer.py'),'--mode',mode])

class V23OrchestrationTests(unittest.TestCase):
    def repo_with_change(self,path='src/a.py',base_text='x=1\n',head_text='x=2\n'):
        td=tempfile.TemporaryDirectory();r=Path(td.name);(r/path).parent.mkdir(parents=True,exist_ok=True);(r/path).write_text(base_text,encoding='utf-8')
        run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);run(['git','config','gc.auto','0'],cwd=r);run(['git','config','maintenance.auto','false'],cwd=r);run(['git','add','.'],cwd=r);run(['git','commit','-qm','base'],cwd=r);base=run(['git','rev-parse','HEAD'],cwd=r).stdout.strip();(r/path).write_text(head_text,encoding='utf-8');run(['git','add','.'],cwd=r);run(['git','commit','-qm','head'],cwd=r);head=run(['git','rev-parse','HEAD'],cwd=r).stdout.strip();ev=r/'evidence.json'
        subprocess.run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head',head,'--work-unit','WU-V23','--output',str(ev)],check=True,text=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=20)
        return td,r,base,head,ev
    def cycle(self,r,ev,case_id='CASE-V23',l1='pass',l2=None,adv=None):
        out=r/f'out-{case_id}';base=json.loads(Path(ev).read_text())['binding']['base_ref_sha'];args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case_id,'--output-dir',str(out),'--l1-cmd-json',cmdjson(l1),'--disable-random-audit']
        if l2:args += ['--l2-cmd-json',cmdjson(l2)]
        if adv:args += ['--adversarial-cmd-json',cmdjson(adv)]
        run(args);return out
    def test_low_risk_l1_pass_completes(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=self.cycle(r,ev)
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'COMPLETE');self.assertEqual(c['required_level'],'L1');self.assertEqual(c['achieved_level'],'L1');self.assertEqual(c['gate_conclusion'],'success')
    def test_auth_path_runs_independent_l2_then_requires_adversarial(self):
        td,r,b,h,ev=self.repo_with_change('auth/session.py');self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-AUTH','pass','pass')
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'ADVERSARIAL_REQUIRED');self.assertEqual(c['required_level'],'ADVERSARIAL');self.assertEqual(c['achieved_level'],'L2')
        l2=json.loads((out/'l2-task.json').read_text());self.assertEqual(l2['lower_layer_result_refs'],[]);self.assertFalse(l2['security_boundary']['prior_review_conclusions_visible']);self.assertTrue(l2['security_boundary']['fresh_context_required'])
        adv=json.loads((out/'adversarial-task.json').read_text());self.assertTrue(adv['security_boundary']['prior_review_conclusions_visible']);self.assertEqual([Path(x).name for x in adv['lower_layer_result_refs']],['l1-review.json','l2-review.json']);self.assertEqual(len(adv['lower_layer_result_digests']),2)
    def test_l1_l2_disagreement_requires_adversarial(self):
        td,r,b,h,ev=self.repo_with_change('requirements.txt','a==1\n','a==2\n');self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-DIS','pass','major')
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'ADVERSARIAL_REQUIRED');self.assertIn('L1_L2_DISAGREEMENT',c['escalation_reasons'])
    def test_governance_path_needs_human_after_adversarial(self):
        td,r,b,h,ev=self.repo_with_change('.github/workflows/release.yml','name: a\n','name: b\n');self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-GOV','pass','pass','pass')
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'HUMAN');self.assertEqual(c['achieved_level'],'ADVERSARIAL');self.assertEqual(c['state'],'HUMAN_REQUIRED');self.assertEqual(c['gate_conclusion'],'action_required')

    def test_head_change_during_review_becomes_stale(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-MUTATE','mutate-head')
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'STALE');self.assertFalse(c['current_head_verified']);self.assertEqual(c['gate_conclusion'],'cancelled')
    def test_shadow_check_preview_is_forced_neutral(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-SHADOW');preview=r/'check.json';run([sys.executable,str(TOOLS/'render_github_check.py'),str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--anchor',str(out/'case-events.anchor.json'),'--output',str(preview)]);j=json.loads(preview.read_text());self.assertEqual(j['conclusion'],'neutral');self.assertTrue(j['name'].startswith('[SHADOW]'))
    def test_enforced_mode_rejects_unattested_isolation(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);cfg=json.loads(json.dumps(__import__('yaml').safe_load((ROOT/'policy/reviewer-routing.yml').read_text())));cfg['mode']='enforced';rp=Path(tempfile.mkstemp(prefix='routing-enforced-',suffix='.yml')[1]);self.addCleanup(lambda: rp.unlink(missing_ok=True));rp.write_text(__import__('yaml').safe_dump(cfg));out=r/'enforced';args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',b,'--case-id','CASE-ENFORCED','--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--routing-policy',str(rp)];env=__import__('os').environ.copy();env['MAESTRO_AUDIT_SEED']='audit-seed';cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,env=env);c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'BLOCKED');self.assertIn('ENFORCED_ATTESTATION_MISSING',c['escalation_reasons'])

    def test_unsafe_reviewer_output_is_rejected(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=r/'unsafe-out';args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',b,'--case-id','CASE-UNSAFE','--output-dir',str(out),'--l1-cmd-json',cmdjson('unsafe-url'),'--disable-random-audit']
        subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True);c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'BLOCKED');self.assertTrue((out/'review-failure.json').exists());self.assertIn('REVIEW_UNSAFE_OUTPUT',c['escalation_reasons'])
    def test_stale_head_cancels_without_review(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);(r/'src/a.py').write_text('x=3\n');run(['git','add','.'],cwd=r);run(['git','commit','-qm','new-head'],cwd=r);out=r/'stale';run([sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',b,'--case-id','CASE-STALE','--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']);c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'STALE');self.assertFalse((out/'l1-review.json').exists())
    def test_ledger_detects_tamper(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-LEDGER');p=out/'case-events.jsonl';rows=p.read_text().splitlines();o=json.loads(rows[0]);o['payload']['repository']='tampered/repo';rows[0]=json.dumps(o);p.write_text('\n'.join(rows)+'\n');cp=subprocess.run([sys.executable,str(TOOLS/'case_ledger.py'),'validate','--ledger',str(p),'--case-id','CASE-LEDGER'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertNotEqual(cp.returncode,0)
    def test_outcome_incident_and_calibration(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-OUTCOME');case=out/'case-record.json';ledger=out/'case-events.jsonl'
        run([sys.executable,str(TOOLS/'ingest_outcome.py'),'--case',str(case),'--ledger',str(ledger),'--author-response','fixed','--merged','true','--merge-sha','a'*40,'--post-merge-status','clean'])
        run([sys.executable,str(TOOLS/'ingest_incident.py'),'--case',str(case),'--ledger',str(ledger),'--incident-ref','INC-1','--failure-family','POST-MERGE-MISS'])
        bank=r/'case-bank'/'CASE-OUTCOME';bank.mkdir(parents=True);__import__('shutil').copy2(case,bank/'case-record.json');__import__('shutil').copy2(ledger,bank/'case-events.jsonl');__import__('shutil').copy2(ledger.with_suffix('.anchor.json'),bank/'case-events.anchor.json');report=r/'calibration.json';run([sys.executable,str(TOOLS/'calibration_report.py'),'--case-bank',str(r/'case-bank'),'--output',str(report)]);j=json.loads(report.read_text());self.assertEqual(j['per_level']['L1']['pass_then_incident'],1)
    def test_standard_candidate_requires_human_codeowner_approval(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);adj=r/'adj.json';o={'schema_version':'2.4','case_id':'CASE-STD','authority_level':'ADVERSARIAL','final_verdict':'FINDINGS','wrong_layers':['L1'],'failure_family_class':'NEW-FAMILY','standard_gap':True,'standard_gap_reason':'Existing standard does not cover the boundary','regression_fixture_recommendation':True,'evidence_refs':['case-record.json'],'confidence':'high','adjudication_digest':''}
        sys.path.insert(0,str(TOOLS));from common import object_digest;o['adjudication_digest']=object_digest(o,'adjudication_digest');adj.write_text(json.dumps(o));out=r/'std.json';run([sys.executable,str(TOOLS/'propose_standard_candidate.py'),'--adjudication',str(adj),'--output',str(out),'--title','Boundary rule','--rule','Require explicit boundary validation','--detection','Static rule plus regression fixture','--machine-enforceable']);s=json.loads(out.read_text());self.assertFalse(s['approval']['approved']);self.assertEqual(s['approval']['required'],['HUMAN','CODEOWNER'])

    def test_blocked_latest_stage_sets_blocked_state(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-BLOCK','block')
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'BLOCKED');self.assertEqual(c['gate_conclusion'],'action_required');self.assertIn('L1_BLOCKED',c['escalation_reasons'])

    def test_effective_routing_policy_digest_is_bound(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup)
        out1=self.cycle(r,ev,'CASE-POLICY-DEFAULT')
        d1=json.loads((out1/'l1-task.json').read_text())['reviewer_contract']['policy_digest'];__import__('shutil').rmtree(out1)
        cfg=json.loads(json.dumps(__import__('yaml').safe_load((ROOT/'policy/reviewer-routing.yml').read_text())));cfg['runtime']['timeout_seconds']=179
        rp=Path(tempfile.mkstemp(prefix='routing-custom-',suffix='.yml')[1]);self.addCleanup(lambda: rp.unlink(missing_ok=True));rp.write_text(__import__('yaml').safe_dump(cfg))
        out2=r/'out-CASE-POLICY-CUSTOM';args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',b,'--case-id','CASE-POLICY-CUSTOM','--output-dir',str(out2),'--l1-cmd-json',cmdjson('pass'),'--routing-policy',str(rp),'--disable-random-audit'];run(args)
        d2=json.loads((out2/'l1-task.json').read_text())['reviewer_contract']['policy_digest']
        self.assertNotEqual(d1,d2)

    def test_stage_risk_escalation_reason_is_preserved(self):
        td,r,b,h,ev=self.repo_with_change();self.addCleanup(td.cleanup);out=self.cycle(r,ev,'CASE-RISK','human-risk')
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'HUMAN');self.assertTrue(any(x.startswith('HUMAN:') for x in c['escalation_reasons']));self.assertIn('L1_REQUEST_HUMAN',c['escalation_reasons'])

if __name__=='__main__':unittest.main()
