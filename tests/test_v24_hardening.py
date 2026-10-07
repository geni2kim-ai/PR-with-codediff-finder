from __future__ import annotations
import copy,json,multiprocessing,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools';sys.path.insert(0,str(TOOLS))
from common import object_digest,named_files_digest
from policy_engine import load_yaml,classify_paths,derive_required_level
from case_ledger import append_event,load_events,validate_events,validate_anchor,default_anchor_path
from queue_policy import choose_queue
from validate_stage_result import validate as validate_stage

def run(cmd,**kw):kw.setdefault('timeout',30);return subprocess.run(cmd,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
def cmdjson(mode):return json.dumps([sys.executable,str(TOOLS/'mock_reviewer.py'),'--mode',mode])
def gitrepo():
    td=tempfile.TemporaryDirectory();r=Path(td.name);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);run(['git','config','gc.auto','0'],cwd=r);return td,r
def commit(r,msg):run(['git','add','-A'],cwd=r);run(['git','commit','-qm',msg],cwd=r);return run(['git','rev-parse','HEAD'],cwd=r).stdout.strip()
def adapter(r,base,head='HEAD',name='ev.json'):
    ev=r/name;run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head',head,'--output',str(ev)]);return ev
def cycle(r,ev,base,case='V24',l1='pass',l2=None,adv=None,out=None):
    out=out or (r/f'out-{case}');args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id',case,'--output-dir',str(out),'--l1-cmd-json',cmdjson(l1),'--disable-random-audit']
    if l2:args+=['--l2-cmd-json',cmdjson(l2)]
    if adv:args+=['--adversarial-cmd-json',cmdjson(adv)]
    run(args);return out

def _append_many(path,case,n,key):
    os.environ['MAESTRO_LEDGER_HMAC_KEY']=key
    for i in range(n):append_event(path,case,'RSI_EVALUATED',{'i':i})

class PathAndGitEvidenceTests(unittest.TestCase):
    def test_segment_anywhere_protected_path_matching(self):
        cfg=load_yaml(ROOT/'policy/protected-paths.yml');h=classify_paths(['backend/auth/providers/google.py','src/auth/oauth/token.py','modules/infra/dns/main.tf','apps/web/.github/workflows/ci.yml','github/workflows/ci.yml'],cfg)
        self.assertIn('backend/auth/providers/google.py',h['adversarial_floor']);self.assertIn('src/auth/oauth/token.py',h['adversarial_floor']);self.assertIn('modules/infra/dns/main.tf',h['human_floor']);self.assertIn('apps/web/.github/workflows/ci.yml',h['governance']);self.assertNotIn('github/workflows/ci.yml',h['governance'])
    def test_rename_out_of_auth_keeps_old_path_floor(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'auth').mkdir();(r/'auth/login.py').write_text('x=1\n');base=commit(r,'base');(r/'lib').mkdir();run(['git','mv','auth/login.py','lib/login.py'],cwd=r);commit(r,'rename');ev=adapter(r,base);j=json.loads(ev.read_text());self.assertIn('auth/login.py',j['summary']['protected_candidates']);out=cycle(r,ev,base,'RENAME','pass','pass');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'ADVERSARIAL')
    def test_merge_base_excludes_base_branch_only_commit(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('a=0\n');(r/'b.py').write_text('b=0\n');root=commit(r,'root');run(['git','branch','feature'],cwd=r);(r/'b.py').write_text('b=main\n');main=commit(r,'main-only');run(['git','checkout','-q','feature'],cwd=r);(r/'a.py').write_text('a=feature\n');head=commit(r,'feature-only');ev=adapter(r,main,head);j=json.loads(ev.read_text());self.assertEqual(j['binding']['base_ref_sha'],main);self.assertEqual(j['binding']['base_sha'],root);self.assertEqual([x['path'] for x in j['files']],['a.py'])
    def test_tampered_evidence_recomputed_digest_is_rejected_against_git(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'auth').mkdir();(r/'src').mkdir();(r/'auth/x.py').write_text('x=1\n');(r/'src/y.py').write_text('y=1\n');base=commit(r,'base');(r/'auth/x.py').write_text('x=2\n');(r/'src/y.py').write_text('y=2\n');commit(r,'head');ev=adapter(r,base);j=json.loads(ev.read_text());j['files']=[f for f in j['files'] if f['path']!='auth/x.py'];j['summary']['files_changed']=len(j['files']);j['summary']['a_lines']=sum(f['lines']['a'] for f in j['files']);j['summary']['b_lines']=sum(f['lines']['b'] for f in j['files']);j['summary']['hunk_count']=sum(f['diff']['hunk_count'] for f in j['files']);j['summary']['changed_lines']=sum(f['diff']['changed_lines'] for f in j['files']);j['summary']['protected_candidates']=[];j['summary']['weakening_signals']=sum((f['weakening_signals'] for f in j['files']),[]);j['summary']['nontext_sensitive_paths']=[];sv={k:v for k,v in j.items() if k not in {'performance','semantic_digest','output_digest'}};j['semantic_digest']=object_digest(sv);j['output_digest']=object_digest(j,'output_digest');tam=r/'tam.json';tam.write_text(json.dumps(j));ev.unlink();out=cycle(r,tam,base,'TAMPER');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'BLOCKED');self.assertIn('EVIDENCE_REJECTED',c['escalation_reasons'])
    def test_tampered_weakening_signal_is_rejected_by_sensor_recompute(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'tests').mkdir();(r/'tests/test_a.py').write_text('def test_a():\n    assert True\n');base=commit(r,'base');(r/'tests/test_a.py').write_text('import pytest\n@pytest.mark.skip\ndef test_a():\n    assert True\n');commit(r,'head');ev=adapter(r,base);j=json.loads(ev.read_text());self.assertTrue(j['summary']['weakening_signals']);j['files'][0]['weakening_signals']=[];j['summary']['weakening_signals']=[];sv={k:v for k,v in j.items() if k not in {'performance','semantic_digest','output_digest'}};j['semantic_digest']=object_digest(sv);j['output_digest']=object_digest(j,'output_digest');tam=r/'tam-weak.json';tam.write_text(json.dumps(j));ev.unlink();out=cycle(r,tam,base,'TAMPER-WEAK');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'BLOCKED');self.assertIn('EVIDENCE_RECOMPUTE_MISMATCH',c['escalation_reasons'])
    def test_symlink_is_untrusted_and_escalates(self):
        if os.name=='nt':self.skipTest('symlink semantics differ on Windows test host')
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');os.symlink('a.py',r/'link.py');commit(r,'symlink');ev=adapter(r,base);j=json.loads(ev.read_text());row=next(x for x in j['files'] if x['path']=='link.py');self.assertTrue(row['symlink']);self.assertFalse(j['trust']['trusted_for_gate']);out=cycle(r,ev,base,'SYMLINK','pass','pass');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'ADVERSARIAL')
    def test_binary_is_untrusted_and_escalates(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'asset.bin').write_bytes(b'\x00\xff\x00abc');commit(r,'bin');ev=adapter(r,base);j=json.loads(ev.read_text());self.assertFalse(j['trust']['trusted_for_gate']);self.assertIn('asset.bin',j['summary']['nontext_sensitive_paths']);out=cycle(r,ev,base,'BIN','pass','pass');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['required_level'],'ADVERSARIAL')

class TraceParityTests(unittest.TestCase):
    def test_trace_api_preserves_findings_stats_and_opcodes(self):
        import importlib.util,random
        cp=ROOT/'vendor/TextDiffChecker_v1.4.6-harness.1/checker.py';spec=importlib.util.spec_from_file_location('tdc_v24_parity',cp);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);rng=random.Random(2404);pool=['alpha','beta','gamma','delta','x=1','x=2','']
        for _ in range(1500):
            a=[rng.choice(pool) for _ in range(rng.randrange(0,18))];b=[rng.choice(pool) for _ in range(rng.randrange(0,18))]
            f1,s1,o1=m.diff_texts_with_opcodes(a,b,'a','b');f2,s2,o2,tr=m.diff_texts_with_trace(a,b,'a','b')
            self.assertEqual(f1,f2);self.assertEqual(o1,o2);self.assertEqual(s1,{k:v for k,v in s2.items() if k!='quality_class'});self.assertIn(s2['quality_class'],{'PROVEN_EXACT','DETERMINISTIC','HEURISTIC','APPROXIMATE'})

class RuntimeIntegrityTests(unittest.TestCase):
    def test_dirty_tracked_worktree_blocks_before_review(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'src').mkdir();(r/'src/a.py').write_text('x=1\n');base=commit(r,'base');(r/'src/a.py').write_text('x=2\n');commit(r,'head');ev=adapter(r,base);(r/'src/a.py').write_text('x=dirty\n');out=cycle(r,ev,base,'DIRTY');c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'BLOCKED');self.assertIn('WORKTREE_DIRTY_BEFORE_REVIEW',c['escalation_reasons']);self.assertFalse((out/'l1-review.json').exists())
    def test_reviewer_failure_is_audited_and_retry_gets_new_attempt(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'src').mkdir();(r/'src/a.py').write_text('x=1\n');base=commit(r,'base');(r/'src/a.py').write_text('x=2\n');commit(r,'head');ev=adapter(r,base);root=r/'attempts';out=cycle(r,ev,base,'FAIL','exit-fail',out=root);c=json.loads((out/'review-cycle.json').read_text());self.assertEqual(c['state'],'BLOCKED');self.assertTrue((out/'review-failure.json').exists());self.assertIn('REVIEW_FAILED',[x['event_type'] for x in load_events(out/'case-events.jsonl')]);args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','FAIL2','--output-dir',str(root),'--retry','--l1-cmd-json',cmdjson('pass'),'--disable-random-audit'];cp=run(args);retry=Path(cp.stdout.strip());self.assertTrue(retry.name.startswith('attempt-'))
    def test_huge_output_is_blocked_without_buffering_in_memory(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'src').mkdir();(r/'src/a.py').write_text('x=1\n');base=commit(r,'base');(r/'src/a.py').write_text('x=2\n');commit(r,'head');ev=adapter(r,base);out=cycle(r,ev,base,'HUGE','huge-output');f=json.loads((out/'review-failure.json').read_text());self.assertEqual(f['failure_kind'],'REVIEW_OUTPUT_LIMIT')
    def test_huge_stderr_is_blocked_without_unbounded_diagnostic_file(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'src').mkdir();(r/'src/a.py').write_text('x=1\n');base=commit(r,'base');(r/'src/a.py').write_text('x=2\n');commit(r,'head');ev=adapter(r,base);out=cycle(r,ev,base,'HUGEERR','huge-stderr');f=json.loads((out/'review-failure.json').read_text());self.assertEqual(f['failure_kind'],'REVIEW_STDERR_LIMIT')

    def test_output_safety_scanner_covers_known_exfiltration_forms(self):
        from sanitize_review_text import scan_text
        for sample in ['www.example.com/x','ftp://example.com/x','//example.com/x','<img src=x>','[x](javascript:alert(1))']:
            f=scan_text(sample);self.assertTrue(f['external_urls_present'] or f['markdown_images_present'],sample)
        self.assertTrue(scan_text('alert-\u200b@owner')['mentions_present'])
    def test_unsafe_source_ref_and_zero_width_mention_are_blocked(self):
        td,r=gitrepo();self.addCleanup(td.cleanup);(r/'src').mkdir();(r/'src/a.py').write_text('x=1\n');base=commit(r,'base');(r/'src/a.py').write_text('x=2\n');commit(r,'head');ev=adapter(r,base);out=cycle(r,ev,base,'UNSAFE','unsafe-url');self.assertEqual(json.loads((out/'review-cycle.json').read_text())['state'],'BLOCKED');out2=cycle(r,ev,base,'MENTION','unsafe-mention');self.assertEqual(json.loads((out2/'review-cycle.json').read_text())['state'],'BLOCKED')

class LedgerTests(unittest.TestCase):
    def test_concurrent_append_and_hmac_anchor_detect_truncation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'events.jsonl';key='test-ledger-key';procs=[multiprocessing.Process(target=_append_many,args=(str(p),'CASE-LEDGER',25,key)) for _ in range(6)]
            [x.start() for x in procs];[x.join(20) for x in procs];self.assertTrue(all(x.exitcode==0 for x in procs));events=load_events(p);self.assertEqual(len(events),150);self.assertFalse(validate_events(events,'CASE-LEDGER'));self.assertFalse(validate_anchor(p,default_anchor_path(p),events,'CASE-LEDGER',key,True));p.write_text('\n'.join(p.read_text().splitlines()[:-1])+'\n');self.assertTrue(validate_anchor(p,default_anchor_path(p),load_events(p),'CASE-LEDGER',key,True))

class PolicyAndProvenanceTests(unittest.TestCase):
    def test_policy_lists_actually_change_escalation(self):
        pcfg=load_yaml(ROOT/'policy/protected-paths.yml');h=classify_paths(['package.json'],pcfg);m={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'};esc=load_yaml(ROOT/'policy/escalation-policy.yml');sensor=load_yaml(ROOT/'policy/sensor-policy.yml');self.assertEqual(derive_required_level(m,h,{},esc,sensor)[0],'L2');esc2=copy.deepcopy(esc);esc2['L2_if_any']=[x for x in esc2['L2_if_any'] if x!='supply_chain_change'];self.assertEqual(derive_required_level(m,h,{},esc2,sensor)[0],'L1')
    def test_runtime_attestation_required_fields_are_policy_driven(self):
        from runtime_attestation import create,validate
        with tempfile.TemporaryDirectory() as td:
            key='k';o=create(td,key);self.assertFalse(validate(o,td,key,['environment_secret_stripping','network_denied']))
            o['network_denied']=False;core={k:v for k,v in o.items() if k!='attestation_hmac'}
            import hashlib,hmac
            from common import canonical_bytes
            o['attestation_hmac']=hmac.new(key.encode(),canonical_bytes(core),hashlib.sha256).hexdigest()
            self.assertIn('runtime attestation missing network_denied=true',validate(o,td,key,['network_denied']))

    def test_named_digest_binds_file_identity_and_missing_ref_fails(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a';b=Path(td)/'b';a.write_text('A');b.write_text('B');d1=named_files_digest([('a',a),('b',b)]);d2=named_files_digest([('a',b),('b',a)]);self.assertNotEqual(d1,d2)
            with self.assertRaises(FileNotFoundError):named_files_digest([('missing',Path(td)/'nope')])
    def test_queue_priority_governance_and_rsi(self):
        self.assertEqual(choose_queue(['RANDOM_AUDIT'],['governance'],None,[]),'governance');self.assertEqual(choose_queue(['RSI_ADVERSARIAL_REQUIRED'],[],{'promotion':{'adversarial_required':True}},[]),'rsi-followup')
    def test_weakening_detection_test_names_no_stream_skip_false_positive(self):
        from textdiff_adapter import is_test_path
        self.assertTrue(is_test_path('__tests__/a.test.ts'));self.assertTrue(is_test_path('pkg/foo_test.go'));self.assertFalse(is_test_path('pkg/testing_utils.py'))

if __name__=='__main__':unittest.main()
