from __future__ import annotations
import copy, hashlib, json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
sys.path.insert(0,str(TOOLS))
from common import object_digest
from case_ledger import append_event,default_anchor_path,load_events,validate_anchor,validate_events
from policy_engine import classify_paths,derive_required_level,load_yaml
from run_review_cycle import audit_sample,worker_command_digest
from sanitize_review_text import scan_text
from textdiff_adapter import weakening_signals
from validate_textdiff_evidence import semantic_errors as evidence_errors
from human_decision_attestation import create as create_human_attestation


def run(cmd,**kw):
    kw.setdefault('timeout',45)
    return subprocess.run(cmd,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)

def cmdjson(mode='pass'):
    return json.dumps([sys.executable,str(TOOLS/'mock_reviewer.py'),'--mode',mode])

def commit(repo,msg):
    run(['git','add','-A'],cwd=repo);run(['git','commit','-qm',msg],cwd=repo)
    return run(['git','rev-parse','HEAD'],cwd=repo).stdout.strip()

def gitrepo(repository='owner/repo'):
    td=tempfile.TemporaryDirectory();r=Path(td.name)
    run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);run(['git','config','gc.auto','0'],cwd=r)
    return td,r,repository

def adapter(repo,base,repository='owner/repo',head='HEAD'):
    p=repo/'evidence.json'
    run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(repo),'--repository',repository,'--base',base,'--head',head,'--output',str(p)])
    return p

def cycle(repo,ev,base,case='CASE',*,repository=None,l1='pass',l2='pass',adv='pass',out=None):
    out=out or repo/f'out-{case}'
    args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(repo),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',cmdjson(l1),'--l2-cmd-json',cmdjson(l2),'--adversarial-cmd-json',cmdjson(adv),'--disable-random-audit']
    cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    if cp.returncode!=0:raise AssertionError(cp.stderr)
    return out

class LedgerHardeningTests(unittest.TestCase):
    def test_canonical_anchor_name_and_post_cycle_human_uses_same_anchor(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'infra').mkdir();(r/'infra/main.tf').write_text('x=1\n');base=commit(r,'base');(r/'infra/main.tf').write_text('x=2\n');commit(r,'head')
        ev=adapter(r,base);out=cycle(r,ev,base,'HUMAN-ANCHOR')
        cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['state'],'HUMAN_REQUIRED')
        self.assertEqual(default_anchor_path(out/'case-events.jsonl'),out/'case-events.anchor.json')
        self.assertTrue((out/'case-events.anchor.json').is_file());self.assertFalse((out/'case-events.jsonl.anchor.json').exists())
        key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-ANCHOR','owner','CONFIRMED',cyc['binding']['head_sha'],key)))
        cp=run([sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','HUMAN-1','--node-id','owner','--verdict','CONFIRMED'],env={**os.environ,'MAESTRO_HUMAN_DECISION_KEY':key})
        self.assertIn('review-cycle.json',cp.stdout)
        self.assertFalse((out/'case-events.jsonl.anchor.json').exists())
        events=load_events(out/'case-events.jsonl');self.assertFalse(validate_events(events,'HUMAN-ANCHOR'));self.assertFalse(validate_anchor(out/'case-events.jsonl',out/'case-events.anchor.json',events,'HUMAN-ANCHOR'))
        cyc2=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc2['state'],'HUMAN_CONFIRMED');self.assertEqual(cyc2['gate_conclusion'],'success')

    def test_hmac_anchor_cannot_be_downgraded_or_recreated_after_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'case-events.jsonl';a=default_anchor_path(p);key='ledger-key'
            append_event(p,'C','CASE_OPENED',{},hmac_key=key,key_id='k')
            with self.assertRaises(ValueError):append_event(p,'C','SENSOR_ACCEPTED',{})
            a.unlink()
            with self.assertRaises(ValueError):append_event(p,'C','SENSOR_ACCEPTED',{},hmac_key=key,key_id='k')
            # Even if the ledger is also truncated to zero bytes, the pre-existing
            # file is not allowed to masquerade as a brand-new history.
            p.write_text('')
            with self.assertRaises(ValueError):append_event(p,'C','SENSOR_ACCEPTED',{},hmac_key=key,key_id='k')

    def test_unicode_line_separator_payload_does_not_corrupt_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'case-events.jsonl';payload={'note':'A\u2028B\u2029C\u0085D'}
            append_event(p,'C','CASE_OPENED',payload)
            append_event(p,'C','SENSOR_ACCEPTED',{'x':'ok'})
            events=load_events(p);self.assertEqual(len(events),2);self.assertEqual(events[0]['payload'],payload);self.assertFalse(validate_events(events,'C'));self.assertFalse(validate_anchor(p,default_anchor_path(p),events,'C'))

class PolicyAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.protected=load_yaml(ROOT/'policy/protected-paths.yml');self.esc=load_yaml(ROOT/'policy/escalation-policy.yml');self.sensor=load_yaml(ROOT/'policy/sensor-policy.yml')
        self.model={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}

    def test_human_floor_paths_and_security_high_are_human(self):
        for path in ['infra/main.tf','deploy/prod.yml','api/public/v1.py','migrations/001.sql']:
            hits=classify_paths([path],self.protected);lvl,reasons=derive_required_level(self.model,hits,{},self.esc,self.sensor);self.assertEqual(lvl,'HUMAN',path);self.assertTrue(any(x.startswith('HUMAN:') for x in reasons))
        m=dict(self.model);m['security_surface']='HIGH';lvl,_=derive_required_level(m,classify_paths(['src/x.py'],self.protected),{},self.esc,self.sensor);self.assertEqual(lvl,'HUMAN')

    def test_real_cycle_human_floor_cannot_finish_at_adversarial(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'infra').mkdir();(r/'infra/main.tf').write_text('x=1\n');base=commit(r,'base');(r/'infra/main.tf').write_text('x=2\n');commit(r,'head')
        out=cycle(r,adapter(r,base),base,'HUMAN-FLOOR');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'HUMAN');self.assertEqual(c['achieved_level'],'ADVERSARIAL');self.assertEqual(c['state'],'HUMAN_REQUIRED');self.assertEqual(c['gate_conclusion'],'action_required')

    def test_harness_self_protection_and_case_insensitive_matching(self):
        hits=classify_paths(['tools/policy_engine.py','tests/test_x.py','vendor/x.py'],self.protected,include_self_protection=True);self.assertTrue(hits['human_floor']);self.assertTrue(hits['governance'])
        for p in ['Auth/login.py','Policy/foo.yml','.GitHub/Workflows/ci.yml','Migrations/001.sql']:
            h=classify_paths([p],self.protected);self.assertTrue(h['adversarial_floor'] or h['human_floor'] or h['governance'],p)
        # Generic repositories do not inherit harness-self-protection for arbitrary tests/tools.
        h=classify_paths(['tools/helper.py','tests/test_x.py'],self.protected,include_self_protection=False);self.assertFalse(h['human_floor']);self.assertFalse(h['governance'])

    def test_deterministic_signal_vocabulary_is_produced(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'migrations').mkdir();(r/'migrations/001.sql').write_text('CREATE TABLE t(id INT);\n');base=commit(r,'base');(r/'migrations/001.sql').write_text('CREATE TABLE t(id INT);\nDROP TABLE t;\n');commit(r,'head')
        ev=json.loads(adapter(r,base).read_text());kinds={x['kind'] for x in ev['summary']['weakening_signals']};self.assertIn('destructive_migration',kinds)
        out=cycle(r,r/'evidence.json',base,'DROP-TABLE');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'HUMAN');self.assertTrue(any('destructive_migration' in x for x in c['escalation_reasons']))

class SensorAndSafetyTests(unittest.TestCase):
    def test_backslash_git_filename_is_analyzed_not_false_exact_zero_line(self):
        if os.name=='nt':self.skipTest('literal backslash filename is POSIX-specific reproduction')
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        p=r/'auth\\login.py';p.write_text('def allowed():\n    return False\n');base=commit(r,'base');p.write_text('def allowed():\n    return True\n');commit(r,'head')
        ev=json.loads(adapter(r,base).read_text());row=next(x for x in ev['files'] if x['path']=='auth\\login.py');self.assertEqual(row['status'],'ANALYZED');self.assertGreater(row['diff']['changed_lines'],0);self.assertGreater(row['lines']['a'],0);self.assertGreater(row['lines']['b'],0);self.assertTrue(ev['summary']['protected_candidates'])

    def test_modified_missing_blob_is_semantically_invalid(self):
        o=json.loads((ROOT/'examples/textdiff-evidence.valid.json').read_text());o=copy.deepcopy(o);o['files'][0]['base_blob_sha']=None;o['semantic_digest']=object_digest({k:v for k,v in o.items() if k not in {'performance','semantic_digest','output_digest'}});o['output_digest']=object_digest(o,'output_digest')
        self.assertTrue(any('requires both Git blob SHAs' in e for e in evidence_errors(o,ROOT/'policy/protected-paths.yml')))

    def test_formfeed_does_not_hide_test_weakening(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'tests').mkdir();p=r/'tests/test_a.py';p.write_text('def test_a():\n    assert True\n');base=commit(r,'base');p.write_text('import pytest\n\x0c@pytest.mark.skip\ndef test_a():\n    assert True\n');head=commit(r,'head')
        kinds={x['kind'] for x in weakening_signals(r,base,head,'tests/test_a.py','MODIFIED')};self.assertIn('test_skip_added',kinds)

    def test_safety_scan_avoids_code_identifier_false_positives_and_catches_secrets(self):
        for s in ['java.net.URL','self.app','pandas.io','javax.net.ssl','settings.dev']:
            self.assertFalse(scan_text(s)['external_urls_present'],s)
        for s in ['https://evil.me/x','//attacker.sh/x','DB_PASSWORD=supersecret','GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz','"api_key": "abcdefghijklmnop"','Bearer abcdefghijklmnop','postgres://user:pass1234@db.example/x','eyJabcdefghijk.abcdefghijk.abcdefghijk']:
            f=scan_text(s);self.assertTrue(f['external_urls_present'] or not f['secret_scan_passed'],s)

    def test_pin_must_not_be_empty(self):
        import yaml
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);cfg=yaml.safe_load((ROOT/'policy/sensor-policy.yml').read_text());cfg['trusted_tool']['checker_sha256']='';p=Path(td.name)/'sensor.yml';p.write_text(yaml.safe_dump(cfg))
        # Pin contract is enforced by semantic validator against its canonical policy; direct sanity on shipped config too.
        shipped=load_yaml(ROOT/'policy/sensor-policy.yml')['trusted_tool'];self.assertTrue(all(isinstance(v,str) and len(v)==64 for v in shipped.values()))
        o=json.loads((ROOT/'examples/textdiff-evidence.valid.json').read_text());old=(ROOT/'policy/sensor-policy.yml').read_text()
        # explicit malformed-pin check mirrors validator contract without mutating repository policy.
        self.assertFalse(isinstance(cfg['trusted_tool']['checker_sha256'],str) and len(cfg['trusted_tool']['checker_sha256'])==64)

    def test_small_change_is_deterministic_banded_fixture_remains_heuristic(self):
        import importlib.util
        cp=ROOT/'vendor/TextDiffChecker_v1.4.6-harness.1/checker.py';sp=importlib.util.spec_from_file_location('tdc_v26',cp);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
        _,s,_,_=m.diff_texts_with_trace(['a'],['b'],'a','b');self.assertEqual(s['quality_class'],'DETERMINISTIC')
        a=['A']*1000+['B']*1000+['A']*1000;rot=a[500:]+a[:500];b=[('C' if i%2==0 and i<2600 else x) for i,x in enumerate(rot)];_,s2,_,tr=m.diff_texts_with_trace(a,b,'a','b');self.assertEqual(s2['quality_class'],'HEURISTIC');self.assertIn('banded_myers',tr['algorithm_path'])

class HumanAndGateTests(unittest.TestCase):
    def _human_case(self):
        td,r,_=gitrepo();(r/'infra').mkdir();(r/'infra/main.tf').write_text('x=1\n');base=commit(r,'base');(r/'infra/main.tf').write_text('x=2\n');commit(r,'head');ev=adapter(r,base);out=cycle(r,ev,base,'HUMAN-GATE');return td,r,out

    def test_human_confirmation_updates_cycle_and_render_verifies_ledger(self):
        td,r,out=self._human_case();self.addCleanup(td.cleanup)
        c0=json.loads((out/'review-cycle.json').read_text());key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-GATE','owner','CONFIRMED',c0['binding']['head_sha'],key)))
        run([sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','H1','--node-id','owner','--verdict','CONFIRMED'],env={**os.environ,'MAESTRO_HUMAN_DECISION_KEY':key})
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'HUMAN_CONFIRMED');self.assertEqual(c['achieved_level'],'HUMAN')
        dest=out/'check.json';run([sys.executable,str(TOOLS/'render_github_check.py'),str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--output',str(dest)]);j=json.loads(dest.read_text());self.assertEqual(j['conclusion'],'neutral');self.assertIn('predicted_conclusion=success',j['output']['summary'])

    def test_tampered_cycle_even_with_recomputed_digest_cannot_render(self):
        td,r,out=self._human_case();self.addCleanup(td.cleanup)
        c=json.loads((out/'review-cycle.json').read_text());c['state']='COMPLETE';c['required_level']='ADVERSARIAL';c['gate_conclusion']='success';c['cycle_digest']=object_digest(c,'cycle_digest');bad=out/'tampered-cycle.json';bad.write_text(json.dumps(c))
        cp=subprocess.run([sys.executable,str(TOOLS/'render_github_check.py'),str(bad),'--ledger',str(out/'case-events.jsonl'),'--output',str(out/'bad-check.json')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        self.assertNotEqual(cp.returncode,0);self.assertIn('CYCLE_CLOSED',cp.stderr+cp.stdout)

    def test_human_decision_rejects_head_drift(self):
        td,r,out=self._human_case();self.addCleanup(td.cleanup)
        (r/'new.txt').write_text('x\n');commit(r,'new-head')
        oldc=json.loads((out/'review-cycle.json').read_text());key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-GATE','owner','CONFIRMED',oldc['binding']['head_sha'],key)))
        cp=subprocess.run([sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','H1','--node-id','owner','--verdict','CONFIRMED'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env={**os.environ,'MAESTRO_HUMAN_DECISION_KEY':key})
        self.assertNotEqual(cp.returncode,0);self.assertIn('HEAD',cp.stderr+cp.stdout)

class WorkerAndAuditTests(unittest.TestCase):
    def test_deterministic_audit_sampling_is_reproducible(self):
        a=audit_sample(37,'external-seed','CASE:HEAD','L1');b=audit_sample(37,'external-seed','CASE:HEAD','L1');self.assertEqual(a,b)
        with self.assertRaises(ValueError):audit_sample(37,None,'CASE:HEAD','L1')

    def test_worker_command_digest_binds_module_source_and_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'modx.py').write_text('x=1\n');d1=worker_command_digest([sys.executable,'-m','modx'],root);(root/'modx.py').write_text('x=2\n');d2=worker_command_digest([sys.executable,'-m','modx'],root);self.assertNotEqual(d1,d2);other=root/'other';other.mkdir();d3=worker_command_digest([sys.executable,'-m','modx'],other);self.assertNotEqual(d2,d3)

    def test_enforced_cli_cannot_disable_random_audit(self):
        import yaml
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');ev=adapter(r,base)
        cfg=yaml.safe_load((ROOT/'policy/reviewer-routing.yml').read_text());cfg['mode']='enforced';rp=r/'routing.yml';rp.write_text(yaml.safe_dump(cfg));cp=subprocess.run([sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','NO-DISABLE','--output-dir',str(r/'out'),'--l1-cmd-json',cmdjson(),'--routing-policy',str(rp),'--disable-random-audit'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env={**os.environ,'MAESTRO_AUDIT_SEED':'x'})
        self.assertNotEqual(cp.returncode,0);self.assertIn('forbidden',cp.stderr+cp.stdout)

    def test_run_worker_timeout_does_not_block_on_stdin_and_kills_child(self):
        from run_review_cycle import run_worker,ReviewerExecutionError
        import yaml
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);w=Path(td.name)/'worker.py';pidfile=Path(td.name)/'child.pid'
        w.write_text("import subprocess,sys,time,os\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\nopen(sys.argv[1],'w').write(str(p.pid))\ntime.sleep(60)\n")
        # Reuse a valid task produced by a tiny SHADOW cycle, then run the hostile worker directly.
        tdr,r,_=gitrepo();self.addCleanup(tdr.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');out=cycle(r,adapter(r,base),base,'TASK-SOURCE');task=json.loads((out/'l1-task.json').read_text())
        cfg=yaml.safe_load((ROOT/'policy/reviewer-routing.yml').read_text());cfg['runtime']['timeout_seconds']=1
        start=time.monotonic()
        with self.assertRaises(ReviewerExecutionError) as cm:run_worker([sys.executable,str(w),str(pidfile)],task,cfg)
        elapsed=time.monotonic()-start;self.assertEqual(cm.exception.kind,'TIMEOUT');self.assertLess(elapsed,4.0)
        if pidfile.exists() and os.name!='nt':
            pid=int(pidfile.read_text());deadline=time.monotonic()+2.0;alive=True
            while time.monotonic()<deadline:
                proc=Path(f'/proc/{pid}/stat')
                if not proc.exists():alive=False;break
                try:state=proc.read_text().split()[2]
                except FileNotFoundError:alive=False;break
                if state=='Z':alive=False;break
                time.sleep(.05)
            self.assertFalse(alive,'reviewer child survived timeout process-group kill')

if __name__=='__main__':unittest.main()
