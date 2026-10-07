from __future__ import annotations
import hashlib,hmac,json,os,subprocess,sys,tempfile,time,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools';sys.path.insert(0,str(TOOLS))
from common import canonical_bytes
from runtime_attestation import create,validate
from run_review_cycle import safe_env


def run(cmd,**kw):kw.setdefault('timeout',30);return subprocess.run(cmd,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
def cmdjson(mode):return json.dumps([sys.executable,str(TOOLS/'mock_reviewer.py'),'--mode',mode])
def commit(r,msg):run(['git','add','-A'],cwd=r);run(['git','commit','-qm',msg],cwd=r);return run(['git','rev-parse','HEAD'],cwd=r).stdout.strip()

class TemporalTrustTests(unittest.TestCase):
    def test_runtime_attestation_is_bound_to_case_and_git_state_and_expires(self):
        with tempfile.TemporaryDirectory() as td:
            key='runtime-key';base='a'*40;head='b'*40;o=create(td,key,case_id='CASE-1',base_sha=base,head_sha=head)
            self.assertEqual(validate(o,td,key,case_id='CASE-1',base_sha=base,head_sha=head),[])
            self.assertIn('runtime attestation case_id mismatch',validate(o,td,key,case_id='CASE-2',base_sha=base,head_sha=head))
            stale=dict(o);stale['issued_at']=(datetime.now(timezone.utc)-timedelta(seconds=600)).isoformat().replace('+00:00','Z');core={k:v for k,v in stale.items() if k!='attestation_hmac'};stale['attestation_hmac']=hmac.new(key.encode(),canonical_bytes(core),hashlib.sha256).hexdigest()
            self.assertIn('runtime attestation stale',validate(stale,td,key,case_id='CASE-1',base_sha=base,head_sha=head,max_age_seconds=300))

    def test_worker_environment_does_not_claim_unverified_sandbox(self):
        task={'runtime_enforcement':{'environment_secret_stripping':True,'network_denied':False,'filesystem_scoped_to_workspace':False}}
        env=safe_env([],task);self.assertEqual(env['MAESTRO_REVIEW_HARNESS'],'1');self.assertEqual(env['MAESTRO_REVIEW_SANDBOX_VERIFIED'],'0');self.assertNotIn('MAESTRO_REVIEW_SANDBOX',env)
        task['runtime_enforcement']['network_denied']=True;task['runtime_enforcement']['filesystem_scoped_to_workspace']=True
        self.assertEqual(safe_env([],task)['MAESTRO_REVIEW_SANDBOX_VERIFIED'],'1')

    def test_base_ref_move_during_review_marks_cycle_stale(self):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);r=Path(td.name);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);run(['git','config','gc.auto','0'],cwd=r)
        (r/'src').mkdir();(r/'src/a.py').write_text('x=1\n');root=commit(r,'root');run(['git','branch','-M','main'],cwd=r);run(['git','checkout','-qb','feature'],cwd=r);(r/'src/a.py').write_text('x=2\n');commit(r,'feature')
        ev=r/'ev.json';run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base','main','--head','HEAD','--output',str(ev)])
        out=r/'out';args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base','main','--case-id','BASE-MOVE','--output-dir',str(out),'--l1-cmd-json',cmdjson('sleep-pass'),'--disable-random-audit']
        p=subprocess.Popen(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=time.time()+8
        while time.time()<deadline and not (out/'l1-task.json').exists():time.sleep(0.02)
        self.assertTrue((out/'l1-task.json').exists(),'review did not reach L1 before base-ref mutation')
        tree=run(['git','rev-parse','main^{tree}'],cwd=r).stdout.strip();new=run(['git','commit-tree',tree,'-p','main'],cwd=r,input='base advanced\n').stdout.strip();run(['git','update-ref','refs/heads/main',new],cwd=r)
        stdout,stderr=p.communicate(timeout=15);self.assertEqual(p.returncode,0,stderr)
        cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['state'],'STALE');self.assertIn('BASE_REF_CHANGED_DURING_REVIEW',cyc['escalation_reasons']);self.assertEqual(cyc['gate_conclusion'],'cancelled')


class ProvenanceHardeningTests(unittest.TestCase):
    def test_worker_command_digest_changes_when_worker_bytes_change(self):
        from run_review_cycle import worker_command_digest
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'worker.py';p.write_text('print(1)\n');d1=worker_command_digest([sys.executable,str(p),'--mode','x']);p.write_text('print(2)\n');d2=worker_command_digest([sys.executable,str(p),'--mode','x']);self.assertNotEqual(d1,d2)

    def test_sensitive_environment_name_is_not_forwarded(self):
        os.environ['AWS_SECRET_ACCESS_KEY']='do-not-forward'
        try:
            env=safe_env(['PATH','AWS_SECRET_ACCESS_KEY'],{'runtime_enforcement':{}});self.assertIn('PATH',env);self.assertNotIn('AWS_SECRET_ACCESS_KEY',env)
        finally:os.environ.pop('AWS_SECRET_ACCESS_KEY',None)

    def test_sensitive_environment_allowlist_blocks_cycle(self):
        import yaml
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);r=Path(td.name);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        ev=r/'ev.json';run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head','HEAD','--output',str(ev)])
        cfg=yaml.safe_load((ROOT/'policy/reviewer-routing.yml').read_text());cfg['runtime']['environment_allowlist'].append('AWS_SECRET_ACCESS_KEY');rp=r/'routing.yml';rp.write_text(yaml.safe_dump(cfg))
        out=r/'out';args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','BAD-ENV','--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--routing-policy',str(rp),'--disable-random-audit'];cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30);self.assertEqual(cp.returncode,0,cp.stderr);cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['state'],'BLOCKED');self.assertIn('RUNTIME_CONFIG_INVALID',cyc['escalation_reasons'])

    def test_enforced_attestation_is_context_bound_and_propagated_to_task(self):
        import yaml
        from runtime_attestation import create as create_att
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);r=Path(td.name);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');head=commit(r,'head')
        ev=r/'ev.json';run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head','HEAD','--output',str(ev)]);e=json.loads(ev.read_text())
        cfg=yaml.safe_load((ROOT/'policy/reviewer-routing.yml').read_text());cfg['mode']='enforced';cfg['reviewers']['L2']['fresh_model_session_attested']=True;cfg['reviewers']['ADVERSARIAL']['fresh_model_session_attested']=True;rp=Path(tempfile.mkstemp(prefix='routing-enforced-',suffix='.yml')[1]);self.addCleanup(lambda: rp.unlink(missing_ok=True));rp.write_text(yaml.safe_dump(cfg))
        key='runtime-key';att=Path(tempfile.mkstemp(prefix='runtime-att-',suffix='.json')[1]);self.addCleanup(lambda: att.unlink(missing_ok=True));att.write_text(json.dumps(create_att(r,key,case_id='ENFORCED-OK',base_sha=e['binding']['base_sha'],head_sha=e['binding']['head_sha'])));out=r/'out';env=os.environ.copy();env.update({'MAESTRO_RUNTIME_ATTESTATION_KEY':key,'MAESTRO_RUNTIME_ATTESTATION_REPLAY_DIR':str(r.parent/('replay-'+r.name)),'MAESTRO_LEDGER_HMAC_KEY':'ledger-key','MAESTRO_AUDIT_SEED':'audit-seed'})
        args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','ENFORCED-OK','--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--routing-policy',str(rp),'--runtime-attestation',str(att)];cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env=env);self.assertEqual(cp.returncode,0,cp.stderr);cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['state'],'COMPLETE');self.assertTrue(cyc['gate_effective']);task=json.loads((out/'l1-task.json').read_text());self.assertTrue(task['runtime_enforcement']['network_denied']);self.assertTrue(task['runtime_enforcement']['filesystem_scoped_to_workspace']);self.assertRegex(task['runtime_enforcement']['runtime_attestation_digest'],r'^[0-9a-f]{64}$')
        events=[json.loads(x) for x in (out/'case-events.jsonl').read_text().splitlines() if x.strip()];self.assertIn('RUNTIME_ATTESTED',[x['event_type'] for x in events])

    def test_stale_enforced_attestation_is_blocked(self):
        import yaml
        from runtime_attestation import create as create_att
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);r=Path(td.name);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head');ev=r/'ev.json';run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head','HEAD','--output',str(ev)]);e=json.loads(ev.read_text())
        cfg=yaml.safe_load((ROOT/'policy/reviewer-routing.yml').read_text());cfg['mode']='enforced';cfg['reviewers']['L2']['fresh_model_session_attested']=True;cfg['reviewers']['ADVERSARIAL']['fresh_model_session_attested']=True;rp=Path(tempfile.mkstemp(prefix='routing-stale-',suffix='.yml')[1]);self.addCleanup(lambda: rp.unlink(missing_ok=True));rp.write_text(yaml.safe_dump(cfg));key='runtime-key';o=create_att(r,key,case_id='ENFORCED-STALE',base_sha=e['binding']['base_sha'],head_sha=e['binding']['head_sha']);o['issued_at']=(datetime.now(timezone.utc)-timedelta(seconds=600)).isoformat().replace('+00:00','Z');core={k:v for k,v in o.items() if k!='attestation_hmac'};o['attestation_hmac']=hmac.new(key.encode(),canonical_bytes(core),hashlib.sha256).hexdigest();att=Path(tempfile.mkstemp(prefix='runtime-stale-',suffix='.json')[1]);self.addCleanup(lambda: att.unlink(missing_ok=True));att.write_text(json.dumps(o));out=r/'out';env=os.environ.copy();env.update({'MAESTRO_RUNTIME_ATTESTATION_KEY':key,'MAESTRO_RUNTIME_ATTESTATION_REPLAY_DIR':str(r.parent/('replay-'+r.name)),'MAESTRO_LEDGER_HMAC_KEY':'ledger-key','MAESTRO_AUDIT_SEED':'audit-seed'});args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','ENFORCED-STALE','--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--routing-policy',str(rp),'--runtime-attestation',str(att)];cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env=env);self.assertEqual(cp.returncode,0,cp.stderr);cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['state'],'BLOCKED');self.assertIn('ENFORCED_ATTESTATION_INVALID',cyc['escalation_reasons'])

    def test_enforced_attestation_nonce_cannot_be_replayed(self):
        import yaml
        from runtime_attestation import create as create_att
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);r=Path(td.name)/'repo';r.mkdir();run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r);(r/'a.py').write_text('x=1\n');base=commit(r,'base');(r/'a.py').write_text('x=2\n');commit(r,'head')
        ev=r/'ev.json';run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head','HEAD','--output',str(ev)]);e=json.loads(ev.read_text())
        cfg=yaml.safe_load((ROOT/'policy/reviewer-routing.yml').read_text());cfg['mode']='enforced';cfg['reviewers']['L2']['fresh_model_session_attested']=True;cfg['reviewers']['ADVERSARIAL']['fresh_model_session_attested']=True;rp=Path(td.name)/'routing.yml';rp.write_text(yaml.safe_dump(cfg))
        key='runtime-key';att=Path(td.name)/'att.json';att.write_text(json.dumps(create_att(r,key,case_id='REPLAY',base_sha=e['binding']['base_sha'],head_sha=e['binding']['head_sha'])));env=os.environ.copy();env.update({'MAESTRO_RUNTIME_ATTESTATION_KEY':key,'MAESTRO_RUNTIME_ATTESTATION_REPLAY_DIR':str(Path(td.name)/'replay-cache'),'MAESTRO_LEDGER_HMAC_KEY':'ledger-key','MAESTRO_AUDIT_SEED':'audit-seed'})
        def once(name):
            out=Path(td.name)/name;args=[sys.executable,str(TOOLS/'run_review_cycle.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','REPLAY','--output-dir',str(out),'--l1-cmd-json',cmdjson('pass'),'--routing-policy',str(rp),'--runtime-attestation',str(att)];cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env=env);self.assertEqual(cp.returncode,0,cp.stderr);return json.loads((out/'review-cycle.json').read_text())
        first=once('out1');self.assertEqual(first['state'],'COMPLETE')
        second=once('out2');self.assertEqual(second['state'],'BLOCKED');self.assertIn('ENFORCED_ATTESTATION_REPLAYED',second['escalation_reasons'])

    def test_ignored_python_bytecode_does_not_dirty_review_workspace(self):
        from run_review_cycle import worktree_dirty
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);r=Path(td.name);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r)
        (r/'.gitignore').write_text('__pycache__/\n*.py[cod]\n');(r/'a.py').write_text('x=1\n');commit(r,'base')
        (r/'tools/__pycache__').mkdir(parents=True);(r/'tools/__pycache__/common.cpython-313.pyc').write_bytes(b'cache')
        dirty=worktree_dirty(r,[]);self.assertEqual(dirty['tracked'],[]);self.assertEqual(dirty['untracked'],[])

if __name__=='__main__':unittest.main()
