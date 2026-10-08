from __future__ import annotations
import copy, hashlib, json, os, shutil, subprocess, sys, tempfile, threading, time, unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
sys.path.insert(0,str(TOOLS))
from common import canonical_bytes,object_digest,sha256_bytes,sha256_file
import case_ledger
from case_ledger import append_event,default_anchor_path,load_events,validate_anchor,validate_events
from policy_engine import classify_paths,derive_required_level,load_yaml
from run_review_cycle import audit_sample,worker_command_digest,finding_disposition,stage_signals,campaign_history,evaluate_review_budget,material_finding_key,authoritative_material_keys,campaign_control_path
from calibration_report import material_state,summarize_cases
import record_human_decision
from sanitize_review_text import scan_text,scan_stage_result
from runtime_attestation import create as create_runtime_attestation, validate as validate_runtime_attestation
from textdiff_adapter import weakening_signals,canonical_source_sha256
from validate_textdiff_evidence import semantic_errors as evidence_errors
import human_decision_attestation
from route_case import reasons_for
from human_decision_attestation import create as create_human_attestation,validate as validate_human_attestation,consume_nonce as consume_human_nonce


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

def cycle(repo,ev,base,case='CASE',*,repository=None,l1='pass',l2='pass',adv='pass',out=None,routing_policy=None,standards=None,spec=None,tests=None):
    out=out or repo/f'out-{case}'
    args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(repo),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',cmdjson(l1),'--l2-cmd-json',cmdjson(l2),'--adversarial-cmd-json',cmdjson(adv),'--disable-random-audit']
    if routing_policy:args+=['--routing-policy',str(routing_policy)]
    for p in standards or []:args+=['--standards-ref',str(p)]
    if spec:args+=['--spec-ref',str(spec)]
    for p in tests or []:args+=['--test-ref',str(p)]
    cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    if cp.returncode!=0:raise AssertionError(cp.stderr)
    return out

def human_env(out,key):
    return {**os.environ,'MAESTRO_HUMAN_DECISION_KEY':key,'MAESTRO_HUMAN_DECISION_REPLAY_DIR':str((Path(out).parent/'.shared-human-replay').resolve())}

class LedgerHardeningTests(unittest.TestCase):
    def test_canonical_anchor_name_and_post_cycle_human_uses_same_anchor(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'infra').mkdir();(r/'infra/main.tf').write_text('x=1\n');base=commit(r,'base');(r/'infra/main.tf').write_text('x=2\n');commit(r,'head')
        ev=adapter(r,base);out=cycle(r,ev,base,'HUMAN-ANCHOR')
        cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['state'],'HUMAN_REQUIRED')
        self.assertEqual(default_anchor_path(out/'case-events.jsonl'),out/'case-events.anchor.json')
        self.assertTrue((out/'case-events.anchor.json').is_file());self.assertFalse((out/'case-events.jsonl.anchor.json').exists())
        key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-ANCHOR','owner','CONFIRMED',cyc['binding']['head_sha'],key,cyc['cycle_digest'],cyc['sensor']['evidence_digest'])))
        cp=run([sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','HUMAN-1','--node-id','owner','--verdict','CONFIRMED'],env=human_env(out,key))
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

    def test_interrupted_ledger_append_recovers_from_authenticated_journal(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'case-events.jsonl';a=default_anchor_path(p);key='ledger-key';txp=case_ledger.pending_append_path(p)
            original_write_anchor=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('simulated anchor crash'))
            try:
                with self.assertRaises(RuntimeError):case_ledger.append_event(p,'C','CASE_OPENED',{'v':1},hmac_key=key,key_id='k')
            finally:
                case_ledger.write_anchor=original_write_anchor
            self.assertTrue(txp.is_file());self.assertEqual(len(load_events(p)),1);self.assertFalse(a.exists())
            original_tx=json.loads(txp.read_text());tampered=copy.deepcopy(original_tx);tampered['event']['payload']['v']=2;txp.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError,'append transaction digest mismatch'):case_ledger.append_event(p,'C','CASE_OPENED',{'v':1},hmac_key=key,key_id='k')
            txp.write_text(json.dumps(original_tx))
            recovered=case_ledger.append_event(p,'C','CASE_OPENED',{'v':1},hmac_key=key,key_id='k')
            self.assertEqual(recovered['seq'],1);self.assertFalse(txp.exists())
            events=load_events(p);self.assertEqual(len(events),1);self.assertEqual(validate_anchor(p,a,events,'C',key,True),[])


    def test_campaign_history_recovers_pending_authenticated_append(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'case-events.jsonl';a=root/'case-events.anchor.json';key='ledger-key';txp=case_ledger.pending_append_path(p)
            original_write_anchor=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('simulated anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    case_ledger.append_event(p,'CAMP-TX','CASE_OPENED',{'head_sha':'a'*40},hmac_key=key,key_id='k')
            finally:
                case_ledger.write_anchor=original_write_anchor
            self.assertTrue(txp.is_file());self.assertTrue(p.is_file());self.assertFalse(a.exists())
            hist=campaign_history(root,'CAMP-TX',key)
            self.assertEqual(len(hist),1);self.assertEqual(hist[0]['state'],'INTERRUPTED_EMPTY');self.assertEqual(hist[0]['head_sha'],'a'*40)
            self.assertFalse(txp.exists());events=load_events(p);self.assertEqual(validate_anchor(p,a,events,'CAMP-TX',key,True),[])

    def test_campaign_history_recovers_pending_append_when_ledger_write_never_landed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'case-events.jsonl';a=root/'case-events.anchor.json';key='ledger-key';txp=case_ledger.pending_append_path(p)
            original_write_anchor=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('simulated anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    case_ledger.append_event(p,'CAMP-TX-PREWRITE','CASE_OPENED',{'head_sha':'b'*40},hmac_key=key,key_id='k')
            finally:
                case_ledger.write_anchor=original_write_anchor
            self.assertTrue(txp.is_file());p.unlink();self.assertFalse(p.exists());self.assertFalse(a.exists())
            hist=campaign_history(root,'CAMP-TX-PREWRITE',key)
            self.assertEqual(len(hist),1);self.assertEqual(hist[0]['state'],'INTERRUPTED_EMPTY');self.assertEqual(hist[0]['head_sha'],'b'*40)
            self.assertTrue(p.is_file());self.assertTrue(a.is_file());self.assertFalse(txp.exists())

    def test_campaign_history_rejects_tampered_pending_append_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'case-events.jsonl';key='ledger-key';txp=case_ledger.pending_append_path(p)
            original_write_anchor=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('simulated anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    case_ledger.append_event(p,'CAMP-TX-TAMPER','CASE_OPENED',{'head_sha':'c'*40},hmac_key=key,key_id='k')
            finally:
                case_ledger.write_anchor=original_write_anchor
            tx=json.loads(txp.read_text());tx['event']['payload']['head_sha']='d'*40;txp.write_text(json.dumps(tx))
            with self.assertRaisesRegex(ValueError,'append transaction digest mismatch'):
                campaign_history(root,'CAMP-TX-TAMPER',key)

    def test_dead_ledger_lock_is_reclaimed_after_process_interruption(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'case-events.jsonl';lock=Path(str(p)+'.lock');lock.write_text('2147483647')
            start=time.monotonic();ev=append_event(p,'C','CASE_OPENED',{});elapsed=time.monotonic()-start
            self.assertEqual(ev['seq'],1);self.assertLess(elapsed,2.0);self.assertFalse(lock.exists())


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

    def test_noncanonical_fork_cannot_delete_self_protection_sentinel(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'tools').mkdir();(r/'policy').mkdir();(r/'src').mkdir()
        (r/'tools/run_review_cycle.py').write_text('gate=True\n');(r/'policy/protected-paths.yml').write_text('x: 1\n');(r/'src/a.py').write_text('x=1\n')
        base=commit(r,'base');(r/'tools/run_review_cycle.py').unlink();commit(r,'delete-gate')
        ev=json.loads(adapter(r,base,repository='fork/noncanonical').read_text())
        self.assertIn('tools/run_review_cycle.py',ev['summary']['protected_candidates'])
        out=cycle(r,r/'evidence.json',base,'DELETE-GATE')
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'HUMAN');self.assertEqual(c['state'],'HUMAN_REQUIRED')

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

    def test_absent_optional_original_package_is_not_echoed_as_verified(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        ev=json.loads(adapter(r,base).read_text());archive=ROOT/'vendor/TextDiffChecker_v1_4_6_original.zip'
        if not archive.is_file():
            self.assertIsNone(ev['tool']['package_sha256'])
            inv=next(x for x in ev['invariants'] if x['id']=='original-package-provenance');self.assertEqual(inv['status'],'not_required')

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
        for s in ['https://evil.me/x','//attacker.sh/x','DB_PASSWORD=supersecret','GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz','"api_key": "abcdefghijklmnop"','Bearer abcdefghijklmnop','postgres://user:pass1234@db.example/x','eyJabcdefghijk.abcdefghijk.abcdefghijk','sk-abcdefghijklmnopqrstuvwxyz','sk-proj-abcdefghijklmnopqrstuvwxyz']:
            f=scan_text(s);self.assertTrue(f['external_urls_present'] or not f['secret_scan_passed'],s)

    def test_pin_must_not_be_empty(self):
        import yaml
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);cfg=yaml.safe_load((ROOT/'policy/sensor-policy.yml').read_text());cfg['trusted_tool']['checker_sha256']='';p=Path(td.name)/'sensor.yml';p.write_text(yaml.safe_dump(cfg))
        # Pin contract is enforced by semantic validator against its canonical policy; direct sanity on shipped config too.
        shipped=load_yaml(ROOT/'policy/sensor-policy.yml')['trusted_tool']
        for k in ('checker_sha256','original_package_sha256','vendor_requirements_sha256','harness_requirements_sha256'):
            self.assertTrue(isinstance(shipped[k],str) and len(shipped[k])==64)
        self.assertIsInstance(shipped.get('original_package_required'),bool)
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
        c0=json.loads((out/'review-cycle.json').read_text());key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-GATE','owner','CONFIRMED',c0['binding']['head_sha'],key,c0['cycle_digest'],c0['sensor']['evidence_digest'])))
        run([sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','H1','--node-id','owner','--verdict','CONFIRMED'],env=human_env(out,key))
        c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'HUMAN_CONFIRMED');self.assertEqual(c['achieved_level'],'HUMAN')
        dest=out/'check.json';run([sys.executable,str(TOOLS/'render_github_check.py'),str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--output',str(dest)],env=human_env(out,key));j=json.loads(dest.read_text());self.assertEqual(j['conclusion'],'neutral');self.assertIn('predicted_conclusion=success',j['output']['summary'])

    def test_tampered_cycle_even_with_recomputed_digest_cannot_render(self):
        td,r,out=self._human_case();self.addCleanup(td.cleanup)
        c=json.loads((out/'review-cycle.json').read_text());c['state']='COMPLETE';c['required_level']='ADVERSARIAL';c['gate_conclusion']='success';c['cycle_digest']=object_digest(c,'cycle_digest');bad=out/'tampered-cycle.json';bad.write_text(json.dumps(c))
        cp=subprocess.run([sys.executable,str(TOOLS/'render_github_check.py'),str(bad),'--ledger',str(out/'case-events.jsonl'),'--output',str(out/'bad-check.json')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        self.assertNotEqual(cp.returncode,0);self.assertIn('CYCLE_CLOSED',cp.stderr+cp.stdout)

    def test_fabricated_human_close_without_signed_decision_cannot_render(self):
        td,r,out=self._human_case();self.addCleanup(td.cleanup)
        c=json.loads((out/'review-cycle.json').read_text());c['achieved_level']='HUMAN';c['state']='HUMAN_CONFIRMED';c['gate_conclusion']='success';c['cycle_digest']='';c['cycle_digest']=object_digest(c,'cycle_digest');(out/'forged.json').write_text(json.dumps(c))
        append_event(out/'case-events.jsonl','HUMAN-GATE','CYCLE_CLOSED',{'state':'HUMAN_CONFIRMED','cycle_digest':c['cycle_digest'],'gate_conclusion':'success','human_review_id':'FORGED','human_attestation_digest':'0'*64},anchor_path=out/'case-events.anchor.json')
        cp=subprocess.run([sys.executable,str(TOOLS/'render_github_check.py'),str(out/'forged.json'),'--ledger',str(out/'case-events.jsonl'),'--output',str(out/'forged-check.json')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env={**os.environ,'MAESTRO_HUMAN_DECISION_KEY':'not-the-signer'})
        self.assertNotEqual(cp.returncode,0);self.assertIn('HUMAN_DECISION',cp.stderr+cp.stdout)

    def test_human_transaction_recovers_after_ledger_commit_before_file_replace(self):
        td,r,out=self._human_case();self.addCleanup(td.cleanup)
        original_case=json.loads((out/'case-record.json').read_text());original_cycle=json.loads((out/'review-cycle.json').read_text())
        key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-GATE','owner','CONFIRMED',original_cycle['binding']['head_sha'],key,original_cycle['cycle_digest'],original_cycle['sensor']['evidence_digest'])))
        args=[sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','RECOVER-1','--node-id','owner','--verdict','CONFIRMED']
        env=human_env(out,key);run(args,env=env)
        final_case=json.loads((out/'case-record.json').read_text());final_cycle=json.loads((out/'review-cycle.json').read_text());events=load_events(out/'case-events.jsonl');count=len(events)
        human=next(x['payload'] for x in events if x['event_type']=='HUMAN_DECISION' and x['payload'].get('review_id')=='RECOVER-1');close=next(x['payload'] for x in events if x['event_type']=='CYCLE_CLOSED' and x['payload'].get('human_review_id')=='RECOVER-1')
        tx={'schema_version':'2.6','request':{'case_id':'HUMAN-GATE','review_id':'RECOVER-1','node_id':'owner','verdict':'CONFIRMED','head_sha':original_cycle['binding']['head_sha'],'attestation_digest':human['attestation_digest'],'source_cycle_digest':original_cycle['cycle_digest'],'evidence_digest':original_cycle['sensor']['evidence_digest'],'transaction_id':sha256_bytes(canonical_bytes({'case_id':'HUMAN-GATE','review_id':'RECOVER-1','attestation_digest':human['attestation_digest'],'source_cycle_digest':original_cycle['cycle_digest']}))},'attestation':json.loads(att.read_text()),'updated_case':final_case,'updated_cycle':final_cycle,'human_event_payload':human,'close_event_payload':close,'transaction_digest':''}
        tx['transaction_digest']=object_digest(tx,'transaction_digest');tx['transaction_hmac']=record_human_decision._transaction_hmac(tx,key)
        (out/'case-record.json').write_text(json.dumps(original_case));(out/'review-cycle.json').write_text(json.dumps(original_cycle));(out/'human-decision-transaction.json').write_text(json.dumps(tx));(out/'human-decision-attestation.json').unlink(missing_ok=True)
        run(args,env=env)
        self.assertEqual(len(load_events(out/'case-events.jsonl')),count);self.assertEqual(json.loads((out/'review-cycle.json').read_text())['state'],'HUMAN_CONFIRMED');self.assertFalse((out/'human-decision-transaction.json').exists());self.assertTrue((out/'human-decision-attestation.json').is_file())

        tampered=json.loads(json.dumps(tx));tampered['updated_cycle']['gate_conclusion']='neutral'
        (out/'case-record.json').write_text(json.dumps(original_case));(out/'review-cycle.json').write_text(json.dumps(original_cycle));(out/'human-decision-transaction.json').write_text(json.dumps(tampered))
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env=env)
        self.assertNotEqual(cp.returncode,0);self.assertIn('human transaction digest mismatch',cp.stderr+cp.stdout)
        tampered['transaction_digest']=object_digest({k:v for k,v in tampered.items() if k!='transaction_hmac'},'transaction_digest')
        (out/'human-decision-transaction.json').write_text(json.dumps(tampered))
        cp2=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env=env)
        self.assertNotEqual(cp2.returncode,0);self.assertIn('human transaction HMAC mismatch',cp2.stderr+cp2.stdout)
        (out/'human-decision-transaction.json').unlink(missing_ok=True)

    def test_human_decision_rejects_head_drift(self):
        td,r,out=self._human_case();self.addCleanup(td.cleanup)
        (r/'new.txt').write_text('x\n');commit(r,'new-head')
        oldc=json.loads((out/'review-cycle.json').read_text());key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-GATE','owner','CONFIRMED',oldc['binding']['head_sha'],key,oldc['cycle_digest'],oldc['sensor']['evidence_digest'])))
        cp=subprocess.run([sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','H1','--node-id','owner','--verdict','CONFIRMED'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env=human_env(out,key))
        self.assertNotEqual(cp.returncode,0);self.assertIn('HEAD',cp.stderr+cp.stdout)

class TrustedInputFreezeTests(unittest.TestCase):
    def test_review_cycle_uses_frozen_policy_refs(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');out=cycle(r,adapter(r,base),base,'POLICY-FREEZE')
        task=json.loads((out/'l1-task.json').read_text());policy_root=(out/'effective-policy').resolve()
        self.assertTrue(task['trusted_refs']['policy'])
        for raw in task['trusted_refs']['policy']:
            p=Path(raw);self.assertTrue(p.is_file());self.assertTrue(str(p).startswith(str(policy_root)))

    def test_review_cycle_freezes_external_standards_spec_and_tests(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');ev=adapter(r,base)
        with tempfile.TemporaryDirectory() as ext:
            ext=Path(ext);std=ext/'standard.md';spec=ext/'spec.md';test=ext/'result.json'
            std.write_text('STANDARD-V1\n');spec.write_text('SPEC-V1\n');test.write_text('{"status":"pass"}\n')
            out=cycle(r,ev,base,'TRUST-FREEZE',standards=[std],spec=spec,tests=[test])
            task=json.loads((out/'l1-task.json').read_text());fstd=Path(task['trusted_refs']['standards'][0]);fspec=Path(task['trusted_refs']['spec']);ftest=Path(task['trusted_refs']['tests'][0])
            self.assertTrue(str(fstd).startswith(str((out/'trusted-inputs').resolve())));self.assertEqual(fstd.read_text(),'STANDARD-V1\n');self.assertEqual(fspec.read_text(),'SPEC-V1\n');self.assertEqual(ftest.read_text(),'{"status":"pass"}\n')
            std.write_text('MUTATED\n');spec.write_text('MUTATED\n');test.write_text('{"status":"fail"}\n')
            self.assertEqual(fstd.read_text(),'STANDARD-V1\n');self.assertEqual(fspec.read_text(),'SPEC-V1\n');self.assertEqual(ftest.read_text(),'{"status":"pass"}\n')


class WorkerAndAuditTests(unittest.TestCase):
    def test_deterministic_audit_sampling_is_reproducible(self):
        a=audit_sample(37,'external-seed','CASE:HEAD','L1');b=audit_sample(37,'external-seed','CASE:HEAD','L1');self.assertEqual(a,b)
        with self.assertRaises(ValueError):audit_sample(37,None,'CASE:HEAD','L1')

    def test_worker_command_digest_binds_module_source_and_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'modx.py').write_text('x=1\n');d1=worker_command_digest([sys.executable,'-m','modx'],root);(root/'modx.py').write_text('x=2\n');d2=worker_command_digest([sys.executable,'-m','modx'],root);self.assertNotEqual(d1,d2);other=root/'other';other.mkdir();d3=worker_command_digest([sys.executable,'-m','modx'],other);self.assertNotEqual(d2,d3)

    def test_module_provenance_does_not_import_package(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pkg=root/'evilpkg';pkg.mkdir();side=pkg/'SIDE_EFFECT'
            (pkg/'__init__.py').write_text("from pathlib import Path\nPath(__file__).with_name('SIDE_EFFECT').write_text('owned')\n")
            (pkg/'worker.py').write_text('x=1\n')
            d=worker_command_digest([sys.executable,'-m','evilpkg.worker'],root)
            self.assertRegex(d,r'^[0-9a-f]{64}$');self.assertFalse(side.exists())

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
                except (FileNotFoundError,ProcessLookupError):alive=False;break
                if state=='Z':alive=False;break
                time.sleep(.05)
            self.assertFalse(alive,'reviewer child survived timeout process-group kill')


class RoutingFreezeTests(unittest.TestCase):
    def _case(self,case_id):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');out=cycle(r,adapter(r,base),base,case_id);return r,out

    def _route_args(self,out,root,extra=None):
        args=[sys.executable,str(TOOLS/'route_case.py'),'--case',str(out/'case-record.json'),'--evidence',str(out/'textdiff-evidence.json'),'--ledger',str(out/'case-events.jsonl'),'--root',str(root),'--l1-ref',str(out/'l1-review.json')]
        if (out/'l2-review.json').is_file():args+=['--l2-ref',str(out/'l2-review.json')]
        return args+(extra or [])

    def test_invalid_mutable_ref_does_not_poison_immutable_destination(self):
        r,out=self._case('ROUTE-BAD');root=r/'routing'
        cp=subprocess.run(self._route_args(out,root,['--standards-ref',str(r/'missing-standard.md')]),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        self.assertNotEqual(cp.returncode,0);self.assertFalse((root/'case-bank/ROUTE-BAD').exists())

    def test_routed_refs_are_frozen_and_queue_retry_is_idempotent(self):
        r,out=self._case('ROUTE-FREEZE');root=r/'routing';std=r/'standard.md';spec=r/'spec.md';test=r/'test-result.json'
        std.write_text('STANDARD-V1\n');spec.write_text('SPEC-V1\n');test.write_text('{"status":"pass"}\n')
        args=self._route_args(out,root,['--standards-ref',str(std),'--spec-ref',str(spec),'--test-ref',str(test)])
        cp=run(args);queue=Path(cp.stdout.strip());packet=json.loads(queue.read_text())
        frozen_std=Path(packet['refs']['trusted_standards'][0]);frozen_spec=Path(packet['refs']['spec_ref']);frozen_test=Path(packet['refs']['test_results'][0])
        self.assertEqual(frozen_std.read_text(),'STANDARD-V1\n');self.assertEqual(frozen_spec.read_text(),'SPEC-V1\n')
        self.assertEqual(packet['digests']['trusted_standards'][0],sha256_file(frozen_std));self.assertEqual(packet['digests']['spec_ref'],sha256_file(frozen_spec));self.assertEqual(packet['digests']['test_results'][0],sha256_file(frozen_test))
        std.write_text('MUTATED\n');spec.unlink();test.unlink();self.assertEqual(frozen_std.read_text(),'STANDARD-V1\n');self.assertEqual(frozen_spec.read_text(),'SPEC-V1\n')
        queue.unlink();cp2=run(args);self.assertEqual(Path(cp2.stdout.strip()),queue);self.assertTrue(queue.is_file())

    def test_existing_case_bank_rejects_changed_case_with_same_id(self):
        r,out=self._case('ROUTE-COLLISION');root=r/'routing'
        args=self._route_args(out,root)
        run(args)
        casep=out/'case-record.json';case=json.loads(casep.read_text());case['outcome']['author_response']='fixed';casep.write_text(json.dumps(case))
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        self.assertNotEqual(cp.returncode,0);self.assertIn('immutable case-bank case mismatch',cp.stderr+cp.stdout)



class FindingTriageTests(unittest.TestCase):
    def _repo(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        return r,base

    def test_nit_is_note_only_and_does_not_invoke_l2(self):
        r,base=self._repo();out=cycle(r,adapter(r,base),base,'TRIAGE-NIT',l1='nit',l2='pass')
        cyc=json.loads((out/'review-cycle.json').read_text())
        notes=json.loads((out/'review-notes.json').read_text())
        self.assertEqual(cyc['required_level'],'L1')
        self.assertEqual(cyc['achieved_level'],'L1')
        self.assertEqual(cyc['state'],'COMPLETE')
        self.assertEqual(cyc['gate_conclusion'],'success')
        self.assertFalse((out/'l2-review.json').exists())
        self.assertFalse(notes['auto_fix'])
        self.assertEqual(notes['authority_effect'],'NONE')
        schema=json.loads((ROOT/'schemas/review-notes.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(notes)),[])
        self.assertEqual([x['severity'] for x in notes['items']],['nit'])
        case=json.loads((out/'case-record.json').read_text())
        self.assertEqual(case['review_trail'][0]['material_finding_count'],0)
        self.assertEqual(case['review_trail'][0]['note_only_finding_count'],1)

    def test_minor_reviewer_escalation_is_suppressed_when_risk_is_baseline(self):
        r,base=self._repo();out=cycle(r,adapter(r,base),base,'TRIAGE-MINOR',l1='minor-escalate',l2='pass')
        cyc=json.loads((out/'review-cycle.json').read_text())
        notes=json.loads((out/'review-notes.json').read_text())
        self.assertEqual(cyc['required_level'],'L1')
        self.assertEqual(cyc['achieved_level'],'L1')
        self.assertEqual(cyc['gate_conclusion'],'success')
        self.assertFalse((out/'l2-review.json').exists())
        self.assertEqual([x['severity'] for x in notes['items']],['minor'])

    def test_major_finding_requires_second_agent_review(self):
        r,base=self._repo();out=cycle(r,adapter(r,base),base,'TRIAGE-MAJOR',l1='major',l2='major')
        cyc=json.loads((out/'review-cycle.json').read_text())
        notes=json.loads((out/'review-notes.json').read_text())
        self.assertEqual(cyc['required_level'],'L2')
        self.assertEqual(cyc['achieved_level'],'L2')
        self.assertTrue((out/'l2-review.json').is_file())
        self.assertFalse((out/'adversarial-review.json').exists())
        self.assertEqual(notes['items'],[])
        self.assertEqual(cyc['gate_conclusion'],'failure')


    def test_semantic_override_minor_requires_l2_and_cannot_gate_success_when_confirmed(self):
        for mode in ('critical-minor','test-integrity-minor'):
            with self.subTest(mode=mode):
                r,base=self._repo();out=cycle(r,adapter(r,base),base,'TRIAGE-'+mode.upper(),l1=mode,l2=mode)
                cyc=json.loads((out/'review-cycle.json').read_text())
                self.assertEqual(cyc['required_level'],'L2')
                self.assertEqual(cyc['achieved_level'],'L2')
                self.assertEqual(cyc['gate_conclusion'],'failure')
                self.assertTrue((out/'l2-review.json').is_file())

    def test_note_only_l1_vs_l2_pass_is_not_downstream_disagreement(self):
        case={'labels':[],'review_trail':[
            {'level':'L1','verdict':'FINDINGS','material_finding_count':0,'note_only_finding_count':1},
            {'level':'L2','verdict':'PASS','material_finding_count':0,'note_only_finding_count':0},
        ],'failure_families':[]}
        self.assertNotIn('L1_L2_DISAGREEMENT',reasons_for(case))

    def test_triage_configuration_cannot_downgrade_major_or_blocker(self):
        hostile={'finding_triage':{'note_only_severities':['minor','nit','major','blocker']},
                 'L2_if_any':[],'ADVERSARIAL_if_any':[],'HUMAN_if_any':[]}
        self.assertEqual(finding_disposition({'severity':'major'},hostile),'AGENT_REVIEW_REQUIRED')
        self.assertEqual(finding_disposition({'severity':'blocker'},hostile),'BLOCKING')
        self.assertEqual(finding_disposition({'severity':'minor','failure_family':'SECURITY-CRITICAL'},hostile),'AGENT_REVIEW_REQUIRED')
        self.assertEqual(finding_disposition({'severity':'nit','failure_family':'GOVERNANCE-TAMPERING'},hostile),'AGENT_REVIEW_REQUIRED')
        self.assertEqual(finding_disposition({'severity':'minor','axis':'test_integrity'},hostile),'AGENT_REVIEW_REQUIRED')
        novel={'confidence':'high','findings':[{'severity':'minor','failure_family':'NOVEL-X','axis':'standards'}],
               'escalation':{'novel_failure_family':True}}
        self.assertTrue(stage_signals(novel,hostile)[0]['novel_failure_family'])
        protected=load_yaml(ROOT/'policy/protected-paths.yml');hits=classify_paths([],protected,include_self_protection=False)
        model={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
        level,reasons=derive_required_level(model,hits,{'major_candidate':True},hostile,{'textdiff':{}})
        self.assertEqual(level,'L2');self.assertIn('L2_FLOOR:major_finding',reasons)
        level2,reasons2=derive_required_level(model,hits,{'blocker_candidate':True},hostile,{'textdiff':{}})
        self.assertEqual(level2,'ADVERSARIAL');self.assertIn('ADVERSARIAL_FLOOR:blocker_finding',reasons2)


class ReviewCampaignBudgetTests(unittest.TestCase):
    def _repo(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        return r,base

    def _retry(self,r,base,case,out,ev,l1='pass',l2='pass',adv='pass'):
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--retry','--l1-cmd-json',cmdjson(l1),'--l2-cmd-json',cmdjson(l2),'--adversarial-cmd-json',cmdjson(adv),'--disable-random-audit']
        return subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)

    def test_budget_evaluator_bounds_same_and_new_material_findings(self):
        history=[{'state':'COMPLETE','material_keys':['family:MOCK-MAJOR']}]
        same=evaluate_review_budget(history,['family:MOCK-MAJOR'],2,3,2)
        self.assertEqual(same['stop_reason'],'SAME_MATERIAL_FINDING_REPEAT');self.assertFalse(same['automated_remediation_retry_allowed'])
        new=evaluate_review_budget(history,['family:OTHER-MAJOR'],2,3,2)
        self.assertIsNone(new['stop_reason']);self.assertTrue(new['automated_remediation_retry_allowed'])
        final=evaluate_review_budget(history,['family:THIRD-MAJOR'],3,3,2)
        self.assertEqual(final['stop_reason'],'AUTOMATED_ATTEMPT_LIMIT');self.assertFalse(final['automated_remediation_retry_allowed'])

    def test_note_only_closeout_cannot_start_retry_loop(self):
        r,base=self._repo();case='BUDGET-NOTE';out=r/'campaign-note';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='nit',out=out)
        cp=self._retry(r,base,case,out,ev,l1='nit')
        self.assertNotEqual(cp.returncode,0);self.assertIn('NOTE_ONLY items remain backlog',cp.stderr+cp.stdout)

    def test_material_retry_requires_changed_head(self):
        r,base=self._repo();case='BUDGET-HEAD';out=r/'campaign-head';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='major',l2='major',out=out)
        cp=self._retry(r,base,case,out,ev,l1='major',l2='major')
        self.assertNotEqual(cp.returncode,0);self.assertIn('requires a new HEAD',cp.stderr+cp.stdout)

    def test_waiting_l1_without_worker_does_not_consume_remediation_attempts(self):
        r,base=self._repo();case='BUDGET-WAIT-L1';out=r/'campaign-wait-l1';ev=adapter(r,base)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--disable-random-audit']
        first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(json.loads((out/'review-cycle.json').read_text())['state'],'WAITING_L1');self.assertEqual(json.loads((out/'review-budget.json').read_text())['attempt_index'],1)
        second=subprocess.run(args+['--retry'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(second.returncode,0,second.stderr)
        d2=Path(second.stdout.strip());self.assertEqual(json.loads((d2/'review-cycle.json').read_text())['state'],'WAITING_L1');self.assertEqual(json.loads((d2/'review-budget.json').read_text())['attempt_index'],1)
        third=subprocess.run(args+['--retry','--l1-cmd-json',cmdjson('pass')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(third.returncode,0,third.stderr)
        d3=Path(third.stdout.strip());self.assertEqual(json.loads((d3/'review-cycle.json').read_text())['state'],'COMPLETE');self.assertEqual(json.loads((d3/'review-budget.json').read_text())['attempt_index'],1)

    def test_waiting_l2_resume_reuses_compatible_l1_in_shadow(self):
        r,base=self._repo();case='BUDGET-RESUME';out=r/'campaign-resume';ev=adapter(r,base)
        with tempfile.TemporaryDirectory() as td:
            counter=Path(td)/'count.txt';worker=Path(td)/'counting_major.py'
            worker.write_text("import pathlib,subprocess,sys\np=pathlib.Path("+repr(str(counter))+")\nn=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\ncp=subprocess.run([sys.executable,"+repr(str(ROOT/'tools/mock_reviewer.py'))+",'--mode','major'],input=sys.stdin.read(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)\nsys.stdout.write(cp.stdout);sys.stderr.write(cp.stderr);raise SystemExit(cp.returncode)\n")
            l1cmd=json.dumps([sys.executable,str(worker)])
            args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',l1cmd,'--disable-random-audit']
            first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(json.loads((out/'review-cycle.json').read_text())['state'],'WAITING_L2');self.assertEqual(counter.read_text(),'1')
            retry=args+['--retry','--l2-cmd-json',cmdjson('major')]
            second=subprocess.run(retry,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(second.returncode,0,second.stderr)
            attempt=Path(second.stdout.strip());cyc=json.loads((attempt/'review-cycle.json').read_text());casej=json.loads((attempt/'case-record.json').read_text())
            self.assertEqual(counter.read_text(),'1')
            self.assertEqual(cyc['state'],'COMPLETE');self.assertIn('lower_stage_reused',casej['labels'])
            budget=json.loads((attempt/'review-budget.json').read_text());self.assertEqual(budget['attempt_index'],1);self.assertEqual(budget['reused_agent_stages'],1);self.assertEqual(budget['executed_agent_stages'],1);self.assertEqual(budget['current_attempt_worker_timeout_budget_seconds'],180)
            events=load_events(attempt/'case-events.jsonl');l1_events=[e for e in events if e['event_type']=='REVIEW_COMPLETED' and e['payload'].get('level')=='L1']
            self.assertEqual(len(l1_events),1);self.assertTrue(l1_events[0]['payload'].get('reused_from_previous_attempt'))

    def test_concurrent_campaign_execution_is_rejected_before_review(self):
        r,base=self._repo();case='BUDGET-CONCURRENT';out=r/'campaign-concurrent';ev=adapter(r,base)
        lock_target=campaign_control_path(out,'case',case)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        with case_ledger.ledger_lock(lock_target,timeout=1.0):
            cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertNotEqual(cp.returncode,0);self.assertIn('same case is not allowed',cp.stderr+cp.stdout)
        self.assertFalse((out/'case-events.jsonl').exists())

    def test_different_case_lock_does_not_serialize_shared_output_root(self):
        r,base=self._repo();out=r/'campaign-shared-lock';ev=adapter(r,base);held_case='LOCK-CASE-A';run_case='LOCK-CASE-B'
        lock_target=campaign_control_path(out,'case',held_case)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',run_case,'--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        with case_ledger.ledger_lock(lock_target,timeout=1.0):
            cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        self.assertEqual(cp.returncode,0,cp.stderr);self.assertTrue((out/'case-events.jsonl').is_file())

    def test_shared_root_history_waits_for_unrelated_ledger_append_lock(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ledger=root/'case-events.jsonl';anchor_path=root/'case-events.anchor.json'
            case_ledger.append_event(ledger,'LOCKED-CASE-A','CASE_OPENED',{'head_sha':'a'*40},anchor_path=anchor_path)
            original_ledger=ledger.read_bytes();original_anchor=anchor_path.read_bytes();result={}
            with case_ledger.ledger_lock(ledger,timeout=1.0):
                ledger.write_text('{"partial":',encoding='utf-8')
                def reader():
                    try:result['history']=campaign_history(root,'LOCKED-CASE-B')
                    except Exception as exc:result['error']=exc
                t=threading.Thread(target=reader);t.start();time.sleep(0.15)
                self.assertTrue(t.is_alive(),'history reader ignored ledger append lock and consumed a partial write')
                ledger.write_bytes(original_ledger);anchor_path.write_bytes(original_anchor)
            t.join(3.0);self.assertFalse(t.is_alive())
            self.assertNotIn('error',result);self.assertEqual(result.get('history'),[])

    def test_unrelated_hmac_case_without_key_blocks_shared_root_case(self):
        r,base=self._repo();out=r/'campaign-shared-hmac';ev=adapter(r,base)
        case_a='SHARED-HMAC-A';case_b='SHARED-HMAC-B'
        args_a=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case_a,'--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp_a=subprocess.run(args_a,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env={**os.environ,'MAESTRO_LEDGER_HMAC_KEY':'case-a-ledger-key'})
        self.assertEqual(cp_a.returncode,0,cp_a.stderr);self.assertTrue(json.loads((out/'case-events.anchor.json').read_text())['hmac_sha256'])
        args_b=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case_b,'--output-dir',str(out),'--retry','--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp_b=subprocess.run(args_b,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertNotEqual(cp_b.returncode,0);self.assertIn('HMAC key unavailable',cp_b.stderr+cp_b.stdout)
        self.assertFalse((out/'attempt-0001'/'case-events.jsonl').exists())

    def test_shared_root_with_active_hmac_authority_rejects_different_unrelated_key(self):
        r,base=self._repo();out=r/'campaign-shared-hmac-authority';ev=adapter(r,base)
        case_a='SHARED-HMAC-AUTH-A';case_b='SHARED-HMAC-AUTH-B'
        args_a=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case_a,'--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp_a=subprocess.run(args_a,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env={**os.environ,'MAESTRO_LEDGER_HMAC_KEY':'root-key-a'})
        self.assertEqual(cp_a.returncode,0,cp_a.stderr)
        args_b=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case_b,'--output-dir',str(out),'--retry','--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp_b=subprocess.run(args_b,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env={**os.environ,'MAESTRO_LEDGER_HMAC_KEY':'root-key-b'})
        self.assertNotEqual(cp_b.returncode,0);self.assertIn('HMAC mismatch',cp_b.stderr+cp_b.stdout)
        self.assertFalse((out/'attempt-0001'/'case-events.jsonl').exists())

    def test_hmac_active_case_cannot_be_relabelled_as_unrelated_to_reset_history(self):
        r,base=self._repo();out=r/'campaign-hmac-relabel';ev=adapter(r,base);case='HMAC-RELABEL-A';key='relabel-key'
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env={**os.environ,'MAESTRO_LEDGER_HMAC_KEY':key});self.assertEqual(cp.returncode,0,cp.stderr)
        ledger=out/'case-events.jsonl';anchorp=out/'case-events.anchor.json';events=load_events(ledger);prev='0'*64
        for e in events:
            e['case_id']='HMAC-RELABEL-B';e['prev_hash']=prev;e['event_hash']='';e['event_hash']=object_digest(e,'event_hash');prev=e['event_hash']
        ledger.write_text(''.join(json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for e in events),encoding='utf-8')
        a=json.loads(anchorp.read_text());a['case_id']='HMAC-RELABEL-B';a['seq']=len(events);a['event_hash']=events[-1]['event_hash'];a['ledger_sha256']=sha256_file(ledger);anchorp.write_text(json.dumps(a))
        with self.assertRaisesRegex(ValueError,'HMAC key unavailable'):
            campaign_history(out,case)
        with self.assertRaisesRegex(ValueError,'HMAC mismatch'):
            campaign_history(out,case,key)

    def test_unrelated_pending_hmac_transaction_without_key_fails_closed_without_mutation(self):
        r,base=self._repo();out=r/'campaign-shared-pending';out.mkdir();ev=adapter(r,base)
        ledger=out/'case-events.jsonl';anchorp=out/'case-events.anchor.json';txp=case_ledger.pending_append_path(ledger)
        original_write_anchor=case_ledger.write_anchor
        case_ledger.write_anchor=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('simulated anchor crash'))
        try:
            with self.assertRaises(RuntimeError):
                case_ledger.append_event(ledger,'SHARED-PENDING-A','CASE_OPENED',{'head_sha':'a'*40},hmac_key='case-a-key',key_id='a')
        finally:
            case_ledger.write_anchor=original_write_anchor
        ledger.unlink();self.assertTrue(txp.is_file());self.assertFalse(anchorp.exists())
        tx_before=txp.read_bytes()
        case_b='SHARED-PENDING-B'
        args_b=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case_b,'--output-dir',str(out),'--retry','--l1-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp_b=subprocess.run(args_b,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertNotEqual(cp_b.returncode,0);self.assertIn('HMAC key unavailable',cp_b.stderr+cp_b.stdout)
        self.assertTrue(txp.is_file());self.assertEqual(txp.read_bytes(),tx_before);self.assertFalse(ledger.exists());self.assertFalse(anchorp.exists())
        self.assertFalse((out/'attempt-0001'/'case-events.jsonl').exists())

    def test_attempt_directory_gap_fails_closed(self):
        r,base=self._repo();case='BUDGET-GAP';out=r/'campaign-gap';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='major',l2='major',out=out)
        (out/'attempt-0002').mkdir()
        cp=self._retry(r,base,case,out,ev,l1='major',l2='major')
        self.assertNotEqual(cp.returncode,0);self.assertIn('attempt layout invalid',cp.stderr+cp.stdout)

    def test_duplicate_replayed_attempt_ledger_fails_closed(self):
        r,base=self._repo();case='BUDGET-DUPLEDGER';out=r/'campaign-dupledger';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='major',l2='major',out=out)
        dup=out/'attempt-0001';dup.mkdir()
        for name in ('case-events.jsonl','case-events.anchor.json','case-record.json'):
            shutil.copy2(out/name,dup/name)
        cp=self._retry(r,base,case,out,ev,l1='major',l2='major')
        self.assertNotEqual(cp.returncode,0);self.assertIn('duplicate/replayed campaign ledger identity',cp.stderr+cp.stdout)

    def test_symlinked_attempt_directory_is_rejected(self):
        if os.name=='nt':self.skipTest('symlink privilege/platform variance on Windows')
        r,base=self._repo();case='BUDGET-SYMLINK';out=r/'campaign-symlink';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='major',l2='major',out=out)
        target=r/'external-attempt';target.mkdir()
        (out/'attempt-0001').symlink_to(target,target_is_directory=True)
        cp=self._retry(r,base,case,out,ev,l1='major',l2='major')
        self.assertNotEqual(cp.returncode,0);self.assertIn('symlinked immutable attempt directory is forbidden',cp.stderr+cp.stdout)

    def test_hmac_shadow_resume_reuses_completed_lower_stage(self):
        r,base=self._repo();case='BUDGET-HMAC-RESUME';out=r/'campaign-hmac-resume';ev=adapter(r,base)
        with tempfile.TemporaryDirectory() as td:
            counter=Path(td)/'count.txt';worker=Path(td)/'counting_major.py'
            worker.write_text("import pathlib,subprocess,sys\np=pathlib.Path("+repr(str(counter))+")\nn=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\ncp=subprocess.run([sys.executable,"+repr(str(ROOT/'tools/mock_reviewer.py'))+",'--mode','major'],input=sys.stdin.read(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)\nsys.stdout.write(cp.stdout);sys.stderr.write(cp.stderr);raise SystemExit(cp.returncode)\n")
            l1cmd=json.dumps([sys.executable,str(worker)]);env={**os.environ,'MAESTRO_LEDGER_HMAC_KEY':'shadow-ledger-key'}
            args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',l1cmd,'--disable-random-audit']
            first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env=env);self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(counter.read_text(),'1')
            second=subprocess.run(args+['--retry','--l2-cmd-json',cmdjson('major')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env=env);self.assertEqual(second.returncode,0,second.stderr)
            d2=Path(second.stdout.strip());budget=json.loads((d2/'review-budget.json').read_text())
            self.assertEqual(counter.read_text(),'1');self.assertEqual(budget['reused_agent_stages'],1);self.assertEqual(budget['attempt_index'],1)

    def _turn_waiting_l2_into_interrupted_l1(self,out,case):
        ledger=out/'case-events.jsonl';anchor=out/'case-events.anchor.json';events=load_events(ledger)
        last_review=max(i for i,e in enumerate(events) if e.get('event_type')=='REVIEW_COMPLETED' and e.get('payload',{}).get('level')=='L1')
        kept=events[:last_review+1]
        ledger.write_text(''.join(json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for e in kept),encoding='utf-8')
        case_ledger.write_anchor(ledger,anchor,case,kept)
        for name in ('case-record.json','review-cycle.json','review-budget.json'):
            (out/name).unlink(missing_ok=True)

    def _turn_waiting_l2_into_started_only_l1(self,out,case):
        ledger=out/'case-events.jsonl';anchor=out/'case-events.anchor.json';events=load_events(ledger)
        started=max(i for i,e in enumerate(events) if e.get('event_type')=='REVIEW_STARTED' and e.get('payload',{}).get('level')=='L1')
        kept=events[:started+1]
        ledger.write_text(''.join(json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for e in kept),encoding='utf-8')
        case_ledger.write_anchor(ledger,anchor,case,kept)
        for name in ('case-record.json','review-cycle.json','review-budget.json'):
            (out/name).unlink(missing_ok=True)

    def test_started_but_uncompleted_review_is_counted_and_not_reused(self):
        r,base=self._repo();case='BUDGET-STARTED-NOT-COMPLETE';out=r/'campaign-started-not-complete';ev=adapter(r,base)
        with tempfile.TemporaryDirectory() as td:
            counter=Path(td)/'count.txt';worker=Path(td)/'counting_major.py'
            worker.write_text("import pathlib,subprocess,sys\np=pathlib.Path("+repr(str(counter))+")\nn=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\ncp=subprocess.run([sys.executable,"+repr(str(ROOT/'tools/mock_reviewer.py'))+",'--mode','major'],input=sys.stdin.read(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)\nsys.stdout.write(cp.stdout);sys.stderr.write(cp.stderr);raise SystemExit(cp.returncode)\n")
            l1cmd=json.dumps([sys.executable,str(worker)])
            args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',l1cmd,'--disable-random-audit']
            first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(counter.read_text(),'1')
            self._turn_waiting_l2_into_started_only_l1(out,case)
            hist=campaign_history(out,case);self.assertEqual(hist[-1]['state'],'INTERRUPTED_EMPTY');self.assertEqual(hist[-1]['worker_invocations'],1)
            second=subprocess.run(args+['--retry','--l2-cmd-json',cmdjson('pass')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(second.returncode,0,second.stderr)
            d2=Path(second.stdout.strip());budget=json.loads((d2/'review-budget.json').read_text())
            self.assertEqual(counter.read_text(),'2')
            self.assertEqual(budget['attempt_index'],1);self.assertEqual(budget['campaign_worker_invocations_used'],3)
            self.assertEqual(budget['campaign_worker_invocation_ceiling'],9)

    def test_started_only_crashes_cannot_bypass_campaign_worker_ceiling(self):
        r,base=self._repo();case='BUDGET-START-CRASH-CEILING';out=r/'campaign-start-crash-ceiling';ev=adapter(r,base)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',cmdjson('major'),'--disable-random-audit']
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp.returncode,0,cp.stderr)
        current=out;self._turn_waiting_l2_into_started_only_l1(current,case)
        for _ in range(8):
            cp=subprocess.run(args+['--retry'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp.returncode,0,cp.stderr)
            current=Path(cp.stdout.strip());self._turn_waiting_l2_into_started_only_l1(current,case)
        hist=campaign_history(out,case);self.assertEqual(sum(x['worker_invocations'] for x in hist),9);self.assertEqual(len(hist),9)
        cp=subprocess.run(args+['--retry','--l2-cmd-json',cmdjson('major')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertNotEqual(cp.returncode,0);self.assertIn('worker invocation budget exhausted',cp.stderr+cp.stdout)

    def test_process_start_failure_is_resumable_and_consumes_worker_invocation(self):
        r,base=self._repo();case='BUDGET-PROCESS-START';out=r/'campaign-process-start';ev=adapter(r,base)
        missing=str(r/'definitely-missing-reviewer-executable')
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',json.dumps([missing]),'--disable-random-audit']
        first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(first.returncode,0,first.stderr)
        hist=campaign_history(out,case);self.assertEqual(hist[-1]['failure_kind'],'REVIEW_PROCESS_START');self.assertTrue(hist[-1]['resumable']);self.assertEqual(hist[-1]['worker_invocations'],1)
        retry=[cmdjson('pass') if x==json.dumps([missing]) else x for x in args]+['--retry']
        second=subprocess.run(retry,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(second.returncode,0,second.stderr)
        d2=Path(second.stdout.strip());budget=json.loads((d2/'review-budget.json').read_text())
        self.assertEqual(budget['attempt_index'],1);self.assertEqual(budget['campaign_worker_invocations_used'],2)

    def test_interrupted_completed_l1_is_reused_instead_of_rerun(self):
        r,base=self._repo();case='BUDGET-INTERRUPTED-REUSE';out=r/'campaign-interrupted-reuse';ev=adapter(r,base)
        with tempfile.TemporaryDirectory() as td:
            counter=Path(td)/'count.txt';worker=Path(td)/'counting_major.py'
            worker.write_text("import pathlib,subprocess,sys\np=pathlib.Path("+repr(str(counter))+")\nn=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\ncp=subprocess.run([sys.executable,"+repr(str(ROOT/'tools/mock_reviewer.py'))+",'--mode','major'],input=sys.stdin.read(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)\nsys.stdout.write(cp.stdout);sys.stderr.write(cp.stderr);raise SystemExit(cp.returncode)\n")
            l1cmd=json.dumps([sys.executable,str(worker)])
            args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',l1cmd,'--disable-random-audit']
            first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(counter.read_text(),'1')
            self._turn_waiting_l2_into_interrupted_l1(out,case)
            hist=campaign_history(out,case);self.assertEqual(hist[-1]['state'],'INTERRUPTED_REVIEW');self.assertEqual(hist[-1]['attempt_index'],1)
            second=subprocess.run(args+['--retry','--l2-cmd-json',cmdjson('major')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(second.returncode,0,second.stderr)
            d2=Path(second.stdout.strip());budget=json.loads((d2/'review-budget.json').read_text())
            self.assertEqual(counter.read_text(),'1');self.assertEqual(budget['attempt_index'],1);self.assertEqual(budget['reused_agent_stages'],1);self.assertEqual(budget['executed_agent_stages'],1)

    def test_interrupted_review_on_old_head_still_consumes_attempt_when_head_changes(self):
        r,base=self._repo();case='BUDGET-INTERRUPTED-HEAD';out=r/'campaign-interrupted-head';ev=adapter(r,base)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',cmdjson('major'),'--disable-random-audit']
        first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(first.returncode,0,first.stderr)
        self._turn_waiting_l2_into_interrupted_l1(out,case)
        (r/'a.py').write_text('x=3\n');run(['git','add','a.py'],cwd=r);run(['git','commit','-qm','new remediation after interrupted review'],cwd=r);ev2=adapter(r,base)
        retry=[str(ev2) if x==str(ev) else x for x in args]+['--retry','--l2-cmd-json',cmdjson('major')]
        second=subprocess.run(retry,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(second.returncode,0,second.stderr)
        d2=Path(second.stdout.strip());self.assertEqual(json.loads((d2/'review-budget.json').read_text())['attempt_index'],2)

    def test_closed_attempt_missing_case_record_fails_closed(self):
        r,base=self._repo();case='BUDGET-CLOSED-NO-CASE';out=r/'campaign-closed-no-case';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='nit',out=out);(out/'case-record.json').unlink()
        cp=self._retry(r,base,case,out,ev,l1='pass')
        self.assertNotEqual(cp.returncode,0);self.assertIn('closed campaign attempt missing case-record',cp.stderr+cp.stdout)

    def _accumulate_process_start_failures(self,r,base,case,out,ev,count):
        missing=str(r/f'missing-worker-{case}')
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',json.dumps([missing]),'--disable-random-audit']
        for i in range(count):
            cp=subprocess.run(args+(['--retry'] if i else []),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
            self.assertEqual(cp.returncode,0,cp.stderr)
        return args

    def test_reviewer_execution_failure_resume_reuses_lower_stage_without_new_remediation_attempt(self):
        r,base=self._repo();case='BUDGET-REVIEW-FAIL-RESUME';out=r/'campaign-review-fail-resume';ev=adapter(r,base)
        with tempfile.TemporaryDirectory() as td:
            counter=Path(td)/'count.txt';worker=Path(td)/'counting_major.py'
            worker.write_text("import pathlib,subprocess,sys\np=pathlib.Path("+repr(str(counter))+")\nn=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\ncp=subprocess.run([sys.executable,"+repr(str(ROOT/'tools/mock_reviewer.py'))+",'--mode','major'],input=sys.stdin.read(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)\nsys.stdout.write(cp.stdout);sys.stderr.write(cp.stderr);raise SystemExit(cp.returncode)\n")
            l1cmd=json.dumps([sys.executable,str(worker)])
            args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',l1cmd,'--l2-cmd-json',cmdjson('exit-fail'),'--disable-random-audit']
            first=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(counter.read_text(),'1');self.assertEqual(json.loads((out/'review-cycle.json').read_text())['state'],'BLOCKED')
            hist=campaign_history(out,case);self.assertTrue(hist[-1]['resumable']);self.assertEqual(hist[-1]['failure_kind'],'REVIEW_PROCESS_EXIT');self.assertEqual(hist[-1]['attempt_index'],1);self.assertEqual(hist[-1]['worker_invocations'],2)
            retry=[cmdjson('major') if x==cmdjson('exit-fail') else x for x in args]+['--retry']
            second=subprocess.run(retry,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(second.returncode,0,second.stderr)
            d2=Path(second.stdout.strip());budget=json.loads((d2/'review-budget.json').read_text());casej=json.loads((d2/'case-record.json').read_text())
            self.assertEqual(counter.read_text(),'1');self.assertEqual(budget['attempt_index'],1);self.assertEqual(budget['reused_agent_stages'],1);self.assertIn('lower_stage_reused',casej['labels'])

    def test_campaign_wide_worker_invocation_ceiling_blocks_retry_before_rerun(self):
        r,base=self._repo();case='BUDGET-WORKER-CEILING';out=r/'campaign-worker-ceiling';ev=adapter(r,base)
        args=self._accumulate_process_start_failures(r,base,case,out,ev,9)
        hist=campaign_history(out,case);self.assertEqual(sum(x['worker_invocations'] for x in hist),9);self.assertEqual({x['attempt_index'] for x in hist},{1});self.assertEqual(len(hist),9)
        cp=subprocess.run(args+['--retry'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertNotEqual(cp.returncode,0);self.assertIn('worker invocation budget exhausted',cp.stderr+cp.stdout)

    def test_worker_ceiling_is_enforced_inside_resume_before_tenth_stage(self):
        r,base=self._repo();case='BUDGET-WORKER-INRUN';out=r/'campaign-worker-inrun';ev=adapter(r,base)
        failing_args=self._accumulate_process_start_failures(r,base,case,out,ev,8)
        hist=campaign_history(out,case);self.assertEqual(sum(x['worker_invocations'] for x in hist),8)
        final_args=failing_args.copy();final_args[final_args.index('--l1-cmd-json')+1]=cmdjson('major')
        cp=subprocess.run(final_args+['--retry','--l2-cmd-json',cmdjson('major')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertEqual(cp.returncode,0,cp.stderr);d=Path(cp.stdout.strip());failure=json.loads((d/'review-failure.json').read_text())
        self.assertEqual(failure['failure_kind'],'REVIEW_CAMPAIGN_WORKER_BUDGET_EXHAUSTED');self.assertFalse((d/'l2-review.json').exists())
        self.assertEqual(json.loads((d/'review-cycle.json').read_text())['state'],'BLOCKED')

    def test_higher_authority_clearance_removes_lower_stage_material_from_budget(self):
        r,base=self._repo();case='BUDGET-CLEARED';out=r/'campaign-cleared';ev=adapter(r,base)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),
              '--l1-cmd-json',cmdjson('major'),'--l2-cmd-json',cmdjson('pass'),'--adversarial-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp.returncode,0,cp.stderr)
        budget=json.loads((out/'review-budget.json').read_text());cyc=json.loads((out/'review-cycle.json').read_text())
        self.assertEqual(cyc['state'],'COMPLETE');self.assertEqual(cyc['gate_conclusion'],'success')
        self.assertEqual(budget['current_material_finding_keys'],[]);self.assertEqual(budget['stop_reason'],'NO_MATERIAL_FINDINGS')
        rows=[('L1',None,{'findings':[{'severity':'major','failure_family':'CORRECTNESS','axis':'correctness_security','path':'a.py'}]},None),
              ('L2',None,{'findings':[]},None)]
        self.assertEqual(authoritative_material_keys(rows,load_yaml(ROOT/'policy/escalation-policy.yml')),[])

    def test_authority_path_resume_keeps_one_logical_attempt_through_adversarial(self):
        r,base=self._repo();case='BUDGET-AUTH-RESUME';out=r/'campaign-auth-resume';ev=adapter(r,base)
        first=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),
               '--l1-cmd-json',cmdjson('major'),'--disable-random-audit']
        cp1=subprocess.run(first,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp1.returncode,0,cp1.stderr)
        self.assertEqual(json.loads((out/'review-budget.json').read_text())['attempt_index'],1)
        second=first+['--retry','--l2-cmd-json',cmdjson('pass')]
        cp2=subprocess.run(second,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp2.returncode,0,cp2.stderr)
        d2=Path(cp2.stdout.strip());self.assertEqual(json.loads((d2/'review-cycle.json').read_text())['state'],'ADVERSARIAL_REQUIRED')
        self.assertEqual(json.loads((d2/'review-budget.json').read_text())['attempt_index'],1)
        third=first+['--retry','--l2-cmd-json',cmdjson('pass'),'--adversarial-cmd-json',cmdjson('pass')]
        cp3=subprocess.run(third,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp3.returncode,0,cp3.stderr)
        d3=Path(cp3.stdout.strip());self.assertEqual(json.loads((d3/'review-cycle.json').read_text())['state'],'COMPLETE')
        self.assertEqual(json.loads((d3/'review-budget.json').read_text())['attempt_index'],1)

    def test_cleared_lower_stage_material_stays_closed_after_unrelated_new_head(self):
        r,base=self._repo();case='BUDGET-CLEARED-CLOSED';out=r/'campaign-cleared-closed';ev=adapter(r,base)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),
              '--l1-cmd-json',cmdjson('major'),'--l2-cmd-json',cmdjson('pass'),'--adversarial-cmd-json',cmdjson('pass'),'--disable-random-audit']
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp.returncode,0,cp.stderr)
        hist=campaign_history(out,case);self.assertEqual(hist[-1]['material_count'],0);self.assertEqual(hist[-1]['material_keys'],[])
        (r/'unrelated.txt').write_text('unrelated\n');run(['git','add','unrelated.txt'],cwd=r);run(['git','commit','-qm','unrelated followup'],cwd=r);ev2=adapter(r,base)
        retry=[str(ev2) if x==str(ev) else x for x in args]+['--retry']
        cp2=subprocess.run(retry,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertNotEqual(cp2.returncode,0);self.assertIn('already closed without material findings',cp2.stderr+cp2.stdout)

    def test_campaign_history_uses_anchored_state_not_mutable_review_cycle_file(self):
        r,base=self._repo();case='BUDGET-STATE-ANCHOR';out=r/'campaign-state-anchor';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='nit',out=out)
        cyc=json.loads((out/'review-cycle.json').read_text());cyc['state']='WAITING_L2';(out/'review-cycle.json').write_text(json.dumps(cyc))
        hist=campaign_history(out,case);self.assertEqual(hist[-1]['state'],'COMPLETE')
        cp=self._retry(r,base,case,out,ev,l1='pass',l2='pass')
        self.assertNotEqual(cp.returncode,0);self.assertIn('already closed without material findings',cp.stderr+cp.stdout)

    def test_campaign_history_rejects_ledger_state_tamper(self):
        r,base=self._repo();case='BUDGET-LEDGER-TAMPER';out=r/'campaign-ledger-tamper';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='nit',out=out)
        ledger=out/'case-events.jsonl';rows=ledger.read_text().splitlines()
        for i,row in enumerate(rows):
            obj=json.loads(row)
            if obj.get('event_type')=='CYCLE_CLOSED':
                obj['payload']['state']='WAITING_L2';rows[i]=json.dumps(obj);break
        ledger.write_text('\n'.join(rows)+'\n')
        cp=self._retry(r,base,case,out,ev,l1='pass',l2='pass')
        self.assertNotEqual(cp.returncode,0);self.assertIn('review campaign history invalid',cp.stderr+cp.stdout)

    def test_campaign_attempt_index_comes_from_anchored_history_not_case_metadata(self):
        r,base=self._repo();case='BUDGET-ATTEMPT-ANCHOR';out=r/'campaign-attempt-anchor';ev=adapter(r,base)
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),
              '--l1-cmd-json',cmdjson('major'),'--disable-random-audit']
        cp1=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp1.returncode,0,cp1.stderr)
        casej=json.loads((out/'case-record.json').read_text());casej['review_campaign']['attempt_index']=99;(out/'case-record.json').write_text(json.dumps(casej))
        second=args+['--retry','--l2-cmd-json',cmdjson('major')]
        cp2=subprocess.run(second,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);self.assertEqual(cp2.returncode,0,cp2.stderr)
        d2=Path(cp2.stdout.strip());self.assertEqual(json.loads((d2/'review-budget.json').read_text())['attempt_index'],1)

    def test_same_material_finding_after_batched_fix_requires_human(self):
        r,base=self._repo();case='BUDGET-REPEAT';out=r/'campaign-repeat';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='major',l2='major',out=out)
        (r/'a.py').write_text('x=3\n');run(['git','add','a.py'],cwd=r);run(['git','commit','-qm','batched remediation'],cwd=r)
        ev2=adapter(r,base);cp=self._retry(r,base,case,out,ev2,l1='major',l2='major')
        self.assertEqual(cp.returncode,0,cp.stderr);attempt=Path(cp.stdout.strip())
        cyc=json.loads((attempt/'review-cycle.json').read_text());budget=json.loads((attempt/'review-budget.json').read_text())
        self.assertEqual(cyc['state'],'HUMAN_REQUIRED');self.assertIn('REVIEW_BUDGET_SAME_MATERIAL_FINDING_REPEAT',cyc['escalation_reasons'])
        self.assertEqual(budget['attempt_index'],2);self.assertEqual(budget['stop_reason'],'SAME_MATERIAL_FINDING_REPEAT');self.assertFalse(budget['automated_remediation_retry_allowed'])
        schema=json.loads((ROOT/'schemas/review-budget.schema.json').read_text());self.assertEqual(list(Draft202012Validator(schema).iter_errors(budget)),[])
        self.assertEqual(len(campaign_history(out,case)),2)

    def test_one_batched_fix_then_pass_closes_campaign(self):
        r,base=self._repo();case='BUDGET-FIXED';out=r/'campaign-fixed';ev=adapter(r,base)
        cycle(r,ev,base,case,l1='major',l2='major',out=out)
        (r/'a.py').write_text('x=3\n');run(['git','add','a.py'],cwd=r);run(['git','commit','-qm','batched remediation'],cwd=r)
        ev2=adapter(r,base);cp=self._retry(r,base,case,out,ev2,l1='pass',l2='pass')
        self.assertEqual(cp.returncode,0,cp.stderr);attempt=Path(cp.stdout.strip())
        cyc=json.loads((attempt/'review-cycle.json').read_text());budget=json.loads((attempt/'review-budget.json').read_text())
        self.assertEqual(cyc['state'],'COMPLETE');self.assertEqual(cyc['gate_conclusion'],'success');self.assertEqual(budget['stop_reason'],'NO_MATERIAL_FINDINGS');self.assertFalse(budget['automated_remediation_retry_allowed'])
        cp2=self._retry(r,base,case,out,ev2,l1='pass')
        self.assertNotEqual(cp2.returncode,0);self.assertIn('already closed without material findings',cp2.stderr+cp2.stdout)


class LeonardoCalibrationTests(unittest.TestCase):
    def _row(self,level,verdict,review_id,material=0,notes=0,major=0,note_key=None,note_family=None,parent=None):
        return {'review_id':review_id,'parent_review_id':parent,'level':level,'node_id':'node','model':None if level=='HUMAN' else {'family':'mock','version':'1'},'verdict':verdict,'confidence':'not_applicable' if level=='HUMAN' else 'high',
                'result_digest':'a'*64,'reviewed_head_sha':'b'*40,'evidence_digest':'c'*64,'input_digest':'d'*64,'prompt_digest':'e'*64,'skill_digest':'f'*64,'policy_digest':'1'*64,'standards_digest':'2'*64,'worker_command_digest':'3'*64,
                'independent_context':level!='L1','requested_level':level,'achieved_level':level,'timestamp':None,'finding_families':[],'material_finding_keys':[],'note_only_finding_families':[note_family] if note_family else [],
                'note_only_finding_keys':[note_key] if note_key else [],'material_finding_count':material,'note_only_finding_count':notes,'major_finding_count':major,'blocker_finding_count':0}

    def test_material_finding_key_distinguishes_same_family_on_different_paths(self):
        a={'failure_family':'CORRECTNESS','axis':'correctness_security','path':'src/a.py'}
        b={'failure_family':'CORRECTNESS','axis':'correctness_security','path':'src/b.py'}
        self.assertNotEqual(material_finding_key(a),material_finding_key(b))
        self.assertEqual(material_finding_key(a),material_finding_key(dict(a,claim='different wording')))

    def test_calibration_treats_note_only_as_material_pass(self):
        l1=self._row('L1','FINDINGS','L1',notes=1,note_key='note-x',note_family='STYLE');l2=self._row('L2','PASS','L2')
        case={'review_trail':[l1,l2],'labels':[],'outcome':{'post_merge_status':'clean'},'review_campaign':{'attempt_index':1,'stop_reason':'NO_MATERIAL_FINDINGS'}}
        s=summarize_cases([case],{'recurring_note_min_occurrences':2})
        self.assertEqual(material_state(l1),'PASS');self.assertEqual(s['per_level']['L1']['agree_final'],1);self.assertNotIn('L1_TO_L2',s['reversals']);self.assertEqual(s['leonardo_metrics']['note_only_rate'],1.0)

    def test_calibration_separates_human_confirmation_from_machine_verdict_vocabulary(self):
        l1=self._row('L1','FINDINGS','L1',material=1,major=1);l2=self._row('L2','PASS','L2');human=self._row('HUMAN','REJECTED','H1',parent='L2')
        case={'review_trail':[l1,l2,human],'labels':[],'outcome':{'post_merge_status':'clean'},'review_campaign':{'attempt_index':2,'stop_reason':'SAME_MATERIAL_FINDING_REPEAT'}}
        s=summarize_cases([case],{'recurring_note_min_occurrences':2})
        self.assertEqual(s['reversals']['L1_TO_L2'],1);self.assertEqual(s['human_decisions']['rejected_parent'],1);self.assertEqual(s['leonardo_metrics']['major_l2_downgrade_rate'],1.0);self.assertEqual(s['leonardo_metrics']['automated_attempts_p95'],2);self.assertEqual(s['leonardo_metrics']['same_material_repeat_rate'],1.0)

    def test_recurring_note_candidate_is_case_frequency_not_stage_frequency(self):
        cases=[]
        for i in range(2):
            l1=self._row('L1','FINDINGS',f'L1-{i}',notes=1,note_key='note-repeat',note_family='STYLE');l2=self._row('L2','PASS',f'L2-{i}',notes=1,note_key='note-repeat',note_family='STYLE')
            cases.append({'review_trail':[l1,l2],'labels':[],'outcome':{'post_merge_status':'clean'}})
        s=summarize_cases(cases,{'recurring_note_min_occurrences':2})
        self.assertEqual(s['leonardo_metrics']['recurring_note_keys'],[{'key':'note-repeat','case_occurrences':2}]);self.assertEqual(s['leonardo_metrics']['recurring_note_families'],[{'failure_family':'STYLE','case_occurrences':2}])


class V26FollowupRegressionTests(unittest.TestCase):
    def test_runtime_fresh_session_attestation_is_fail_closed_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            key='runtime-key';base='a'*40;head='b'*40
            default=create_runtime_attestation(td,key,case_id='CASE',base_sha=base,head_sha=head)
            errs=validate_runtime_attestation(default,td,key,['l2_fresh_session','adversarial_fresh_session'],case_id='CASE',base_sha=base,head_sha=head)
            self.assertIn('runtime attestation missing l2_fresh_session=true',errs)
            self.assertIn('runtime attestation missing adversarial_fresh_session=true',errs)
            explicit=create_runtime_attestation(td,key,case_id='CASE',base_sha=base,head_sha=head,l2_fresh_session=True,adversarial_fresh_session=True)
            self.assertEqual(validate_runtime_attestation(explicit,td,key,['l2_fresh_session','adversarial_fresh_session'],case_id='CASE',base_sha=base,head_sha=head),[])


    def test_human_attestation_is_cycle_bound_and_one_time(self):
        key='human-key';head='a'*40;cycle='b'*64;evidence='c'*64
        att=create_human_attestation('CASE','owner','CONFIRMED',head,key,cycle,evidence)
        self.assertEqual(validate_human_attestation(att,case_id='CASE',actor_id='owner',verdict='CONFIRMED',head_sha=head,cycle_digest=cycle,evidence_digest=evidence,key=key),[])
        self.assertIn('human attestation cycle_digest mismatch',validate_human_attestation(att,case_id='CASE',actor_id='owner',verdict='CONFIRMED',head_sha=head,cycle_digest='d'*64,evidence_digest=evidence,key=key))
        with tempfile.TemporaryDirectory() as td:
            err,_=consume_human_nonce(att,td,'tx-1');self.assertIsNone(err)
            err,_=consume_human_nonce(att,td,'tx-1');self.assertIsNone(err)
            err,_=consume_human_nonce(att,td,'tx-2');self.assertEqual(err,'human attestation replay detected')

    def test_source_ref_repository_paths_are_not_external_hosts(self):
        result={'findings':[{'claim':'x','evidence':'x','impact':'x','recommendation':'x','source_ref':'src/a.py:1','failure_family':'PATH-CHECK'}],'escalation':{'reasons':[]}}
        self.assertFalse(scan_stage_result(result)['external_urls_present'])
        result['findings'][0]['source_ref']='evil.me'
        self.assertTrue(scan_stage_result(result)['external_urls_present'])

    def test_canonical_source_hash_uses_actual_worktree_bytes_but_normalizes_eol(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'checker.py';p.write_bytes(b'print(1)\r\n')
            d1=canonical_source_sha256(p)
            p.write_bytes(b'print(1)\n');self.assertEqual(d1,canonical_source_sha256(p))
            p.write_bytes(b'print(2)\n');self.assertNotEqual(d1,canonical_source_sha256(p))
            p.write_bytes(b'print(2)\\n');self.assertNotEqual(d1,canonical_source_sha256(p))

    def test_shadow_cycle_runs_without_external_audit_seed(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'src').mkdir();(r/'src/a.py').write_text('x=1\\n');base=commit(r,'base');(r/'src/a.py').write_text('x=2\\n');commit(r,'head');ev=adapter(r,base)
        out=r/'out';env={k:v for k,v in os.environ.items() if k!='MAESTRO_AUDIT_SEED'}
        cp=subprocess.run([sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','SHADOW-NO-SEED','--output-dir',str(out),'--l1-cmd-json',cmdjson()],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env=env)
        self.assertEqual(cp.returncode,0,cp.stderr)
        case=json.loads((out/'case-record.json').read_text());self.assertIn('random_audit_shadow_unseeded',case.get('labels',[]))


class V26CodexFollowupTests(unittest.TestCase):
    def test_bare_domains_are_scanned_in_all_reviewer_text_fields(self):
        base={'claim':'x','evidence':'x','impact':'x','recommendation':'x','source_ref':'src/a.py:1','failure_family':'PATH-CHECK'}
        for field in ('claim','evidence','impact','recommendation','failure_family'):
            finding=dict(base);finding[field]='download.attacker.example.com'
            self.assertTrue(scan_stage_result({'findings':[finding],'escalation':{'reasons':[]}})['external_urls_present'],field)
        self.assertTrue(scan_stage_result({'findings':[base],'escalation':{'reasons':['attacker.example.com']}})['external_urls_present'])
        self.assertFalse(scan_stage_result({'findings':[base],'escalation':{'reasons':[]}})['external_urls_present'])

    def test_worker_command_digest_binds_pythonpath_module_bytes(self):
        with tempfile.TemporaryDirectory() as cwd, tempfile.TemporaryDirectory() as ext:
            p=Path(ext)/'external_worker.py';p.write_text('VALUE=1\n')
            d1=worker_command_digest([sys.executable,'-m','external_worker'],cwd,pythonpath=ext)
            p.write_text('VALUE=2\n');d2=worker_command_digest([sys.executable,'-m','external_worker'],cwd,pythonpath=ext)
            self.assertNotEqual(d1,d2)

    def test_workflow_requires_committed_manifest_for_pr(self):
        s=(ROOT/'.github/workflows/harness-validation.yml').read_text()
        self.assertIn('Require committed manifest on PR/manual validation',s)
        self.assertIn('cmp -s MANIFEST.sha256 MANIFEST.generated.sha256',s)
        self.assertIn("github.event.pull_request.head.sha",s)
        self.assertLess(s.index('Require committed manifest on PR/manual validation'),s.index('Apply generated manifest for hardening-branch push validation'))
        self.assertNotIn('git push origin HEAD:hardening/v2.6',s)

    def test_runtime_cli_fail_closes_fresh_session_claims(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);key='runtime-key';bad=root/'bad.json';good=root/'good.json';env={**os.environ,'MAESTRO_RUNTIME_ATTESTATION_KEY':key}
            run([sys.executable,str(TOOLS/'runtime_attestation.py'),'create','--workspace',str(root),'--output',str(bad)],env=env)
            cp=subprocess.run([sys.executable,str(TOOLS/'runtime_attestation.py'),'validate','--workspace',str(root),'--attestation',str(bad)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env=env)
            self.assertNotEqual(cp.returncode,0);self.assertIn('l2_fresh_session=true',cp.stdout+cp.stderr)
            run([sys.executable,str(TOOLS/'runtime_attestation.py'),'create','--workspace',str(root),'--output',str(good),'--l2-fresh-session','--adversarial-fresh-session'],env=env)
            run([sys.executable,str(TOOLS/'runtime_attestation.py'),'validate','--workspace',str(root),'--attestation',str(good)],env=env)

    def test_human_attestation_freshness_is_only_an_acceptance_window(self):
        key='human-key';head='a'*40;cycle='b'*64;evidence='c'*64
        att=create_human_attestation('CASE','owner','CONFIRMED',head,key,cycle,evidence)
        att['issued_at']=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat().replace('+00:00','Z')
        core={k:v for k,v in att.items() if k!='attestation_hmac'};att['attestation_hmac']=human_decision_attestation._mac(core,key)
        fresh_errs=validate_human_attestation(att,case_id='CASE',actor_id='owner',verdict='CONFIRMED',head_sha=head,cycle_digest=cycle,evidence_digest=evidence,key=key,max_age_seconds=300)
        self.assertIn('human attestation stale',fresh_errs)
        self.assertEqual(validate_human_attestation(att,case_id='CASE',actor_id='owner',verdict='CONFIRMED',head_sha=head,cycle_digest=cycle,evidence_digest=evidence,key=key,enforce_freshness=False),[])

    def test_human_decision_requires_external_shared_replay_cache(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'infra').mkdir();(r/'infra/main.tf').write_text('x=1\n');base=commit(r,'base');(r/'infra/main.tf').write_text('x=2\n');commit(r,'head')
        out=cycle(r,adapter(r,base),base,'HUMAN-REPLAY');cyc=json.loads((out/'review-cycle.json').read_text());key='human-key';att=out/'human-att.json';att.write_text(json.dumps(create_human_attestation('HUMAN-REPLAY','owner','CONFIRMED',cyc['binding']['head_sha'],key,cyc['cycle_digest'],cyc['sensor']['evidence_digest'])))
        args=[sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--attestation',str(att),'--review-id','H1','--node-id','owner','--verdict','CONFIRMED']
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,env={**os.environ,'MAESTRO_HUMAN_DECISION_KEY':key})
        self.assertNotEqual(cp.returncode,0);self.assertIn('shared human replay cache',cp.stderr+cp.stdout)
        run(args,env=human_env(out,key))

    def test_route_case_rejects_tampered_self_digests(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');out=cycle(r,adapter(r,base),base,'ROUTE-DIGEST')
        root=r/'routing';args=[sys.executable,str(TOOLS/'route_case.py'),'--case',str(out/'case-record.json'),'--evidence',str(out/'textdiff-evidence.json'),'--ledger',str(out/'case-events.jsonl'),'--root',str(root),'--l1-ref',str(out/'l1-review.json')]
        ev=json.loads((out/'textdiff-evidence.json').read_text());ev['tool']['product_version']='tampered';(out/'textdiff-evidence.json').write_text(json.dumps(ev))
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20);self.assertNotEqual(cp.returncode,0);self.assertIn('invalid evidence',cp.stderr+cp.stdout)
        td2,r2,_=gitrepo();self.addCleanup(td2.cleanup);(r2/'a.py').write_text('x=1\n');base2=commit(r2,'base');(r2/'a.py').write_text('x=2\n');commit(r2,'head');out2=cycle(r2,adapter(r2,base2),base2,'ROUTE-REVIEW')
        review=json.loads((out2/'l1-review.json').read_text());review['confidence']='low' if review['confidence']!='low' else 'high';(out2/'l1-review.json').write_text(json.dumps(review))
        args2=[sys.executable,str(TOOLS/'route_case.py'),'--case',str(out2/'case-record.json'),'--evidence',str(out2/'textdiff-evidence.json'),'--ledger',str(out2/'case-events.jsonl'),'--root',str(r2/'routing'),'--l1-ref',str(out2/'l1-review.json')]
        cp2=subprocess.run(args2,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20);self.assertNotEqual(cp2.returncode,0);self.assertIn('review invalid',cp2.stderr+cp2.stdout)

    def test_route_case_freezes_effective_routing_override(self):
        import yaml
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        cfg=yaml.safe_load((ROOT/'policy/reviewer-routing.yml').read_text());cfg['reviewers']['L1']['node_id']='L1-override';rp=Path(tempfile.mkstemp(prefix='routing-override-',suffix='.yml')[1]);self.addCleanup(lambda: rp.unlink(missing_ok=True));rp.write_text(yaml.safe_dump(cfg))
        out=cycle(r,adapter(r,base),base,'ROUTE-POLICY',routing_policy=rp);root=r/'routing'
        cp=subprocess.run([sys.executable,str(TOOLS/'route_case.py'),'--case',str(out/'case-record.json'),'--evidence',str(out/'textdiff-evidence.json'),'--ledger',str(out/'case-events.jsonl'),'--root',str(root),'--l1-ref',str(out/'l1-review.json')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertEqual(cp.returncode,0,cp.stderr)
        packet=json.loads(Path(cp.stdout.strip()).read_text());frozen=Path(packet['refs']['deterministic_policy']).parent/'policy'/'reviewer-routing.yml'
        self.assertEqual(yaml.safe_load(frozen.read_text())['reviewers']['L1']['node_id'],'L1-override')

    def test_route_case_uses_cycle_frozen_policy_after_live_policy_changes(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        out=cycle(r,adapter(r,base),base,'ROUTE-FROZEN-POLICY');root=r/'routing'
        policy=ROOT/'policy/protected-paths.yml';original=policy.read_bytes()
        try:
            policy.write_bytes(original+b'\n# live policy changed after completed review\n')
            cp=subprocess.run([sys.executable,str(TOOLS/'route_case.py'),'--case',str(out/'case-record.json'),'--evidence',str(out/'textdiff-evidence.json'),'--ledger',str(out/'case-events.jsonl'),'--root',str(root),'--l1-ref',str(out/'l1-review.json')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        finally:
            policy.write_bytes(original)
        self.assertEqual(cp.returncode,0,cp.stderr)
        packet=json.loads(Path(cp.stdout.strip()).read_text());policy_dir=Path(packet['refs']['deterministic_policy']).parent/'policy'
        self.assertEqual((policy_dir/'protected-paths.yml').read_bytes(),(out/'effective-policy/protected-paths.yml').read_bytes())

    def test_route_case_uses_cycle_frozen_trusted_inputs_after_live_mutation(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup)
        (r/'a.py').write_text('x=1\n');(r/'std.md').write_text('STANDARD-ORIGINAL\n');(r/'spec.md').write_text('SPEC-ORIGINAL\n');(r/'test.json').write_text('{"status":"pass","version":1}\n');base=commit(r,'base')
        (r/'a.py').write_text('x=2\n');commit(r,'head')
        out=cycle(r,adapter(r,base),base,'ROUTE-FROZEN-INPUTS',standards=[r/'std.md'],spec=r/'spec.md',tests=[r/'test.json'])
        (r/'std.md').write_text('STANDARD-MUTATED\n');(r/'spec.md').write_text('SPEC-MUTATED\n');(r/'test.json').write_text('{"status":"fail","version":2}\n')
        root=r/'routing';cp=subprocess.run([sys.executable,str(TOOLS/'route_case.py'),'--case',str(out/'case-record.json'),'--evidence',str(out/'textdiff-evidence.json'),'--ledger',str(out/'case-events.jsonl'),'--root',str(root),'--l1-ref',str(out/'l1-review.json'),'--standards-ref',str(r/'std.md'),'--spec-ref',str(r/'spec.md'),'--test-ref',str(r/'test.json')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertEqual(cp.returncode,0,cp.stderr)
        packet=json.loads(Path(cp.stdout.strip()).read_text())
        self.assertEqual(Path(packet['refs']['trusted_standards'][0]).read_text(),'STANDARD-ORIGINAL\n')
        self.assertEqual(Path(packet['refs']['spec_ref']).read_text(),'SPEC-ORIGINAL\n')
        self.assertEqual(Path(packet['refs']['test_results'][0]).read_text(),'{"status":"pass","version":1}\n')
        self.assertNotEqual(packet['digests']['trusted_standards'][0],sha256_file(r/'std.md'))

    def test_route_case_recovery_rejects_corrupted_case_bank_refs(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        out=cycle(r,adapter(r,base),base,'ROUTE-RECOVERY-INTEGRITY');root=r/'routing'
        args=[sys.executable,str(TOOLS/'route_case.py'),'--case',str(out/'case-record.json'),'--evidence',str(out/'textdiff-evidence.json'),'--ledger',str(out/'case-events.jsonl'),'--root',str(root),'--l1-ref',str(out/'l1-review.json')]
        first=run(args);packet_path=Path(first.stdout.strip());cb=root/'case-bank'/'ROUTE-RECOVERY-INTEGRITY'
        (cb/'l1-review.json').write_text('{"corrupted":true}\n')
        packet_path.unlink()
        cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertNotEqual(cp.returncode,0);self.assertIn('case-bank L1 review invalid',cp.stderr+cp.stdout);self.assertFalse(packet_path.exists())

    def test_outcome_and_incident_transactions_recover_after_ledger_append(self):
        td,r,_=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');out=cycle(r,adapter(r,base),base,'TX-RECOVER')
        casep=out/'case-record.json';ledger=out/'case-events.jsonl';original=json.loads(casep.read_text())
        outcome_args=[sys.executable,str(TOOLS/'ingest_outcome.py'),'--case',str(casep),'--ledger',str(ledger),'--author-response','fixed','--merged','true','--merge-sha','a'*40,'--post-merge-status','clean']
        run(outcome_args);final_outcome=json.loads(casep.read_text());events=load_events(ledger);count=len(events);payload=[e['payload'] for e in events if e['event_type']=='OUTCOME_RECORDED'][-1]
        request=dict(payload);tx={'schema_version':'2.6','request':request,'event_type':'OUTCOME_RECORDED','event_payload':payload,'updated_case':final_outcome,'transaction_digest':''};tx['transaction_digest']=object_digest(tx,'transaction_digest')
        casep.write_text(json.dumps(original));(out/'outcome-transaction.json').write_text(json.dumps(tx));run(outcome_args)
        self.assertEqual(len(load_events(ledger)),count);self.assertEqual(json.loads(casep.read_text())['outcome'],payload)
        before_incident=json.loads(casep.read_text());incident_args=[sys.executable,str(TOOLS/'ingest_incident.py'),'--case',str(casep),'--ledger',str(ledger),'--incident-ref','INC-1','--kind','incident','--failure-family','SECURITY-CRITICAL']
        run(incident_args);final_incident=json.loads(casep.read_text());events=load_events(ledger);count2=len(events);ip=[e['payload'] for e in events if e['event_type']=='INCIDENT_RECORDED'][-1]
        ireq={'incident_ref':'INC-1','kind':'incident','failure_family':'SECURITY-CRITICAL'};itx={'schema_version':'2.6','request':ireq,'event_type':'INCIDENT_RECORDED','event_payload':ip,'updated_case':final_incident,'transaction_digest':''};itx['transaction_digest']=object_digest(itx,'transaction_digest')
        casep.write_text(json.dumps(before_incident));(out/'incident-transaction.json').write_text(json.dumps(itx));run(incident_args)
        self.assertEqual(len(load_events(ledger)),count2);self.assertEqual(json.loads(casep.read_text())['outcome']['incident_ref'],'INC-1')

    @unittest.skipIf(os.name=='nt','POSIX process-group regression')
    def test_validation_group_kills_descendants_after_pass(self):
        from run_validation import _run_group
        with tempfile.TemporaryDirectory() as td:
            pidfile=Path(td)/'child.pid';mod=ROOT/'tests'/'_tmp_v26_child_leak.py'
            mod.write_text("import subprocess,sys,unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n def test_leak(self):\n  p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n  Path("+repr(str(pidfile))+").write_text(str(p.pid))\n")
            try:
                ok,count,detail=_run_group('tests._tmp_v26_child_leak.T.test_leak',10);self.assertTrue(ok,detail);self.assertEqual(count,1);pid=int(pidfile.read_text());deadline=time.monotonic()+2;alive=True
                while time.monotonic()<deadline:
                    stat=Path(f'/proc/{pid}/stat')
                    if not stat.exists():alive=False;break
                    try:state=stat.read_text().split()[2]
                    except (FileNotFoundError,ProcessLookupError):alive=False;break
                    if state=='Z':alive=False;break
                    time.sleep(.05)
                self.assertFalse(alive,'passing validation group leaked a descendant')
            finally:mod.unlink(missing_ok=True)

    def test_readme_human_example_includes_binding_digests_and_shared_cache(self):
        s=(ROOT/'README.md').read_text();self.assertIn('--cycle-digest <review-cycle.cycle_digest>',s);self.assertIn('--evidence-digest <case-record.sensor.evidence_digest>',s);self.assertIn('MAESTRO_HUMAN_DECISION_REPLAY_DIR',s)


if __name__=='__main__':unittest.main()
