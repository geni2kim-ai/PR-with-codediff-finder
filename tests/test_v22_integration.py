from __future__ import annotations
import copy, importlib.util, json, subprocess, sys, tempfile, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from policy_engine import load_yaml,classify_paths,derive_required_level
from validate_textdiff_evidence import semantic_errors as evidence_errors
from validate_rsi_evaluation import semantic_errors as rsi_errors
from validate_case_record import semantic_errors as case_errors

class V22SemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev=json.loads((ROOT/'examples/textdiff-evidence.valid.json').read_text())
        cls.rsi=json.loads((ROOT/'examples/rsi-evaluation.valid.json').read_text())
        cls.case=json.loads((ROOT/'examples/case-record.valid.json').read_text())
    def test_tampered_evidence_digest_rejected(self):
        x=copy.deepcopy(self.ev);x['output_digest']='0'*64
        self.assertIn('output_digest mismatch',evidence_errors(x,ROOT/'policy/protected-paths.yml'))
    def test_semantic_digest_ignores_performance_but_output_digest_does_not(self):
        from common import object_digest
        x=copy.deepcopy(self.ev);old_sem=x['semantic_digest'];old_out=x['output_digest'];x['performance']['elapsed_ms'] += 123.456
        semantic_view={k:v for k,v in x.items() if k not in {'performance','semantic_digest','output_digest'}}
        self.assertEqual(old_sem, object_digest(semantic_view))
        x['output_digest']=object_digest(x,'output_digest')
        self.assertNotEqual(old_out,x['output_digest'])
        self.assertFalse(evidence_errors(x,ROOT/'policy/protected-paths.yml'))
    def test_false_proven_exact_path_rejected(self):
        x=copy.deepcopy(self.ev);f=x['files'][0];f['diff']['quality_class']='PROVEN_EXACT';x['summary']['quality_class']='PROVEN_EXACT'
        self.assertTrue(any('heuristic path cannot be PROVEN_EXACT' in z for z in evidence_errors(x,ROOT/'policy/protected-paths.yml')))
    def test_size_limit_gap_cannot_claim_trusted_gate(self):
        from common import object_digest
        x=copy.deepcopy(self.ev);f=x['files'][0];f['status']='SKIPPED';f['skip_reason']='size_limit';f['diff']={'hunk_count':0,'changed_lines':0,'approx':False,'quality_class':'NOT_APPLICABLE','algorithm_path':[],'trace_digest':'0'*64}
        x['summary']['hunk_count']=sum(y['diff']['hunk_count'] for y in x['files']);x['summary']['changed_lines']=sum(y['diff']['changed_lines'] for y in x['files']);qs=[y['diff']['quality_class'] for y in x['files'] if y['status']=='ANALYZED'];order={'PROVEN_EXACT':0,'HEURISTIC':1,'APPROXIMATE':2};x['summary']['quality_class']=max(qs,key=lambda q:order[q]) if qs else 'NOT_APPLICABLE'
        x['trust']['trusted_for_gate']=True;semantic_view={k:v for k,v in x.items() if k not in {'performance','semantic_digest','output_digest'}};x['semantic_digest']=object_digest(semantic_view);x['output_digest']=object_digest(x,'output_digest')
        self.assertTrue(any('trusted_for_gate must be false' in z for z in evidence_errors(x,ROOT/'policy/protected-paths.yml')))
    def test_tampered_rsi_score_rejected(self):
        x=copy.deepcopy(self.rsi);x['overall_score']=0.01
        self.assertTrue(any('overall_score mismatch' in z for z in rsi_errors(x,ROOT/'policy/rsi-scoring.yml')))
    def test_duplicate_review_id_rejected(self):
        x=copy.deepcopy(self.case);x['review_trail'].append(copy.deepcopy(x['review_trail'][0]))
        self.assertTrue(any('duplicate review_id' in z for z in case_errors(x)))
    def test_adversarial_must_be_independent(self):
        x=copy.deepcopy(self.case);r=copy.deepcopy(x['review_trail'][-1]);r.update({'review_id':'ADV-1','parent_review_id':x['review_trail'][-1]['review_id'],'level':'ADVERSARIAL','requested_level':'ADVERSARIAL','achieved_level':'ADVERSARIAL','independent_context':False});x['review_trail'].append(r)
        self.assertTrue(any('ADVERSARIAL must use independent_context' in z for z in case_errors(x)))
    def test_sensor_heuristic_high_risk_escalates(self):
        cfg=load_yaml(ROOT/'policy/protected-paths.yml');hits=classify_paths(['auth/session.py'],cfg)
        model={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'MEDIUM','availability_criticality':'LOW'}
        lvl,_=derive_required_level(model,hits,{'sensor_heuristic_high_risk':True})
        self.assertEqual(lvl,'ADVERSARIAL')
    def test_untrusted_sensor_escalates_at_least_l2(self):
        cfg=load_yaml(ROOT/'policy/protected-paths.yml');hits=classify_paths(['src/x.py'],cfg)
        model={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
        lvl,_=derive_required_level(model,hits,{'sensor_runtime_untrusted':True})
        self.assertEqual(lvl,'L2')

class TextDiffFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=ROOT/'vendor/TextDiffChecker_v1.4.6-harness.1';spec=importlib.util.spec_from_file_location('tdc_fixture',root/'checker.py');cls.c=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.c)
    @staticmethod
    def cost(ops):return sum((i2-i1)+(j2-j1) for t,i1,i2,j1,j2 in ops if t!='equal')
    def test_diff_false_exact_fixture_is_not_proven(self):
        a=['A']*1000+['B']*1000+['A']*1000;rot=a[500:]+a[:500];b=[('C' if i%2==0 and i<2600 else x) for i,x in enumerate(rot)]
        _,s,ops,tr=self.c.diff_texts_with_trace(a,b,'a','b');_,sx,opsx,trx=self.c.diff_texts_with_trace(a,b,'a','b',exact=True)
        self.assertEqual(s['quality_class'],'HEURISTIC');self.assertGreater(self.cost(ops),self.cost(opsx));self.assertEqual(sx['quality_class'],'PROVEN_EXACT')

class AdapterSmokeTest(unittest.TestCase):
    def test_git_adapter(self):
        if subprocess.run(['git','--version'],stdout=subprocess.DEVNULL).returncode: self.skipTest('git unavailable')
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);subprocess.run(['git','init','-q'],cwd=r,check=True);subprocess.run(['git','config','user.email','t@example.com'],cwd=r,check=True);subprocess.run(['git','config','user.name','t'],cwd=r,check=True)
            (r/'auth').mkdir();(r/'tests').mkdir();(r/'auth/x.py').write_text('ALLOW=True\n');(r/'tests/test_x.py').write_text('def test_x():\n    assert True\n')
            subprocess.run(['git','add','.'],cwd=r,check=True);subprocess.run(['git','commit','-qm','base'],cwd=r,check=True);base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
            (r/'auth/x.py').write_text('ALLOW=False\n');(r/'tests/test_x.py').write_text('@pytest.mark.skip\ndef test_x():\n    assert True\n');(r/'new.py').write_text('x=1\n')
            subprocess.run(['git','add','.'],cwd=r,check=True);subprocess.run(['git','commit','-qm','head'],cwd=r,check=True);head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip();out=r/'e.json'
            subprocess.run([sys.executable,str(ROOT/'tools/textdiff_adapter.py'),'--repo',str(r),'--repository','owner/repo','--base',base,'--head',head,'--output',str(out)],check=True)
            ev=json.loads(out.read_text());self.assertFalse(evidence_errors(ev,ROOT/'policy/protected-paths.yml'));self.assertIn('auth/x.py',ev['summary']['protected_candidates']);self.assertTrue(any(x['kind']=='test_skip_added' for x in ev['summary']['weakening_signals']))
            added=next(x for x in ev['files'] if x['path']=='new.py');self.assertEqual(added['change_type'],'ADDED');self.assertIsNone(added['encoding']['base']);self.assertEqual(added['encoding']['head'],'utf-8')

if __name__=='__main__':unittest.main()
