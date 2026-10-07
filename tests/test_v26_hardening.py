from __future__ import annotations
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools';sys.path.insert(0,str(TOOLS))
from common import object_digest
from policy_engine import load_yaml,classify_paths,derive_required_level
from case_ledger import append_event,load_events,default_anchor_path
from sanitize_review_text import scan_text

def run(cmd,**kw):
    kw.setdefault('timeout',40)
    return subprocess.run(cmd,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
def commit(r,msg):
    run(['git','add','-A'],cwd=r);run(['git','commit','-qm',msg],cwd=r);return run(['git','rev-parse','HEAD'],cwd=r).stdout.strip()
def cmdjson(mode='pass'):
    return json.dumps([sys.executable,str(TOOLS/'mock_reviewer.py'),'--mode',mode])

class V26HardeningTests(unittest.TestCase):
    def test_case_insensitive_harness_paths_are_protected(self):
        cfg=load_yaml(ROOT/'policy/protected-paths.yml')
        h=classify_paths(['Auth/login.py','Policy/x.yml','.GitHub/Workflows/ci.yml','tools/policy_engine.py'],cfg)
        self.assertIn('Auth/login.py',h['adversarial_floor']);self.assertIn('Policy/x.yml',h['governance'])
        self.assertIn('.GitHub/Workflows/ci.yml',h['governance']);self.assertIn('tools/policy_engine.py',h['human_floor'])

    def test_human_floor_and_security_high_require_human(self):
        cfg=load_yaml(ROOT/'policy/protected-paths.yml');esc=load_yaml(ROOT/'policy/escalation-policy.yml');sensor=load_yaml(ROOT/'policy/sensor-policy.yml')
        model={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
        level,_=derive_required_level(model,classify_paths(['infra/main.tf'],cfg),{},esc,sensor);self.assertEqual(level,'HUMAN')
        model=dict(model);model['security_surface']='HIGH'
        level,_=derive_required_level(model,classify_paths(['src/a.py'],cfg),{},esc,sensor);self.assertEqual(level,'HUMAN')

    def test_anchor_name_and_unicode_payload(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';append_event(ledger,'CASE-U','RSI_EVALUATED',{'note':'a\u2028b\u2029c\u0085d'})
            self.assertEqual(default_anchor_path(ledger).name,'case-events.anchor.json');self.assertEqual(len(load_events(ledger)),1)

    def test_protected_anchor_cannot_be_replaced_by_keyless_append(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';append_event(ledger,'CASE-H','RSI_EVALUATED',{'i':1},hmac_key='test-key',key_id='test')
            with self.assertRaises(ValueError):append_event(ledger,'CASE-H','RSI_EVALUATED',{'i':2})

    def test_normal_code_identifiers_are_not_external_urls(self):
        for value in ['java.net.URL','self.app','pandas.io','javax.net.ssl','settings.dev']:
            self.assertFalse(scan_text(value)['external_urls_present'])

    @unittest.skipIf(os.name=='nt','POSIX Git backslash-filename regression')
    def test_backslash_git_filename_is_read_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r)
            p=r/('auth'+'\\'+'login.py');p.write_text('x=False\n');base=commit(r,'base');p.write_text('x=True\n');commit(r,'head')
            ev=r/'ev.json';run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head','HEAD','--output',str(ev)])
            o=json.loads(ev.read_text());f=o['files'][0];self.assertEqual(f['path'],'auth\\login.py');self.assertEqual(f['status'],'ANALYZED');self.assertGreater(f['diff']['changed_lines'],0)
            self.assertIsNotNone(f['base_blob_sha']);self.assertIsNotNone(f['head_blob_sha'])

    def test_human_floor_cycle_can_be_closed_by_human(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);run(['git','init','-q'],cwd=r);run(['git','config','user.email','t@example.com'],cwd=r);run(['git','config','user.name','t'],cwd=r)
            (r/'infra').mkdir();(r/'infra/main.tf').write_text('x=1\n');base=commit(r,'base');(r/'infra/main.tf').write_text('x=2\n');commit(r,'head')
            ev=r/'ev.json';run([sys.executable,str(TOOLS/'textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head','HEAD','--output',str(ev)])
            out=r/'out';run([sys.executable,str(TOOLS/'run_review_cycle_v26.py'),'--repo',str(r),'--evidence',str(ev),'--expected-base',base,'--case-id','HF','--output-dir',str(out),'--l1-cmd-json',cmdjson(),'--l2-cmd-json',cmdjson(),'--adversarial-cmd-json',cmdjson(),'--disable-random-audit'])
            cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['required_level'],'HUMAN');self.assertEqual(cyc['state'],'HUMAN_REQUIRED')
            run([sys.executable,str(TOOLS/'record_human_decision.py'),'--case',str(out/'case-record.json'),'--cycle',str(out/'review-cycle.json'),'--ledger',str(out/'case-events.jsonl'),'--repo',str(r),'--review-id','H1','--actor','owner','--verdict','CONFIRMED'])
            cyc=json.loads((out/'review-cycle.json').read_text());self.assertEqual(cyc['state'],'HUMAN_CONFIRMED');self.assertEqual(cyc['gate_conclusion'],'success')

if __name__=='__main__':unittest.main()
