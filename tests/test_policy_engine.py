import copy, json, unittest, sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from policy_engine import load_yaml,classify_paths,derive_risk,derive_required_level,gate_conclusion
from validate_review_result import semantic_errors

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load_yaml(ROOT/'policy/protected-paths.yml')
        self.base=json.loads((ROOT/'examples/review-result.valid.json').read_text())
        self.schema=json.loads((ROOT/'schemas/review-result.schema.json').read_text())
    def test_issue_template_not_blanket_governance(self):
        h=classify_paths(['.github/ISSUE_TEMPLATE/bug.md'],self.cfg)
        self.assertFalse(h['governance'])
    def test_workflow_forces_governance_human(self):
        h=classify_paths(['.github/workflows/release.yml'],self.cfg)
        m={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
        r=derive_risk(m,h); self.assertTrue(r['governance_change']); self.assertTrue(r['human_review_required'])
        self.assertEqual(derive_required_level(m,h,{})[0],'HUMAN')
    def test_auth_forces_adversarial_but_path_alone_not_human(self):
        h=classify_paths(['auth/session.py'],self.cfg)
        m={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'MEDIUM','availability_criticality':'LOW'}
        self.assertFalse(derive_risk(m,h)['human_review_required'])
        self.assertEqual(derive_required_level(m,h,{})[0],'ADVERSARIAL')
    def test_hard_reversibility_requires_human(self):
        h=classify_paths(['src/x.py'],self.cfg)
        m={'reversibility':'HARD','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
        self.assertTrue(derive_risk(m,h)['human_review_required'])
        self.assertEqual(derive_required_level(m,h,{})[0],'HUMAN')
    def test_pass_plus_unreached_authority_is_action_required(self):
        self.assertEqual(gate_conclusion(self.base),'action_required')
    def test_pass_blocker_counterexample_schema_rejected(self):
        r=copy.deepcopy(self.base)
        r['findings']=[{'finding_id':'F','axis':'correctness_security','severity':'blocker','confidence':'high','certainty':'confirmed','path':'x','line':1,'hunk':None,'claim':'x','evidence':'x','source_ref':None,'impact':'x','recommendation':'x','preexisting':False,'activated_or_worsened':True,'duplicate_of':None,'failure_family':None}]
        r['summary']['finding_counts']={'blocker':1,'major':0,'minor':0,'nit':0}
        self.assertTrue(list(Draft202012Validator(self.schema).iter_errors(r)))
    def test_hard_human_false_counterexample_schema_rejected(self):
        r=copy.deepcopy(self.base); r['risk']['model_assessment']['reversibility']='HARD'; r['risk']['harness']['human_review_required']=False
        self.assertTrue(list(Draft202012Validator(self.schema).iter_errors(r)))
    def test_governance_requires_human_level_schema(self):
        r=copy.deepcopy(self.base); r['risk']['harness']['governance_change']=True; r['authority']['required_level']='ADVERSARIAL'
        self.assertTrue(list(Draft202012Validator(self.schema).iter_errors(r)))
    def test_unknown_check_blocks_pass_semantically(self):
        r=copy.deepcopy(self.base); r['deterministic_checks'][0]['status']='unknown'
        self.assertTrue(any('unknown deterministic checks' in e for e in semantic_errors(r)))
    def test_spec_post_open_author_change_escalates(self):
        r=copy.deepcopy(self.base)
        r['spec_ref']={'kind':'issue','locator':'#1','source_sha256':'1'*64,'resolved_at':None,'modified_at':None,'pr_opened_at':None,'modified_after_pr_open':True,'modified_by_pr_author':True,'post_open_change_explained':False,'trust_status':'WARNING'}
        r['authority']['required_level']='L2'; r['risk']['model_assessment']['security_surface']='LOW'; r['risk']['harness']['human_review_required']=False; r['risk']['harness']['floor_human_review_required']=False; r['risk']['harness']['floor_reasons']=[]
        paths=['src/x.py']
        self.assertTrue(any('ADVERSARIAL' in e for e in semantic_errors(r,paths)))

if __name__=='__main__': unittest.main()

class SensorAuthorityV22Tests(unittest.TestCase):
    def setUp(self):
        self.base=json.loads((ROOT/'examples/review-result.valid.json').read_text())
    def test_untrusted_sensor_cannot_remain_l1(self):
        r=copy.deepcopy(self.base)
        r['sensor_context']['trusted_for_gate']=False
        r['risk']['model_assessment']={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
        r['risk']['harness']={'governance_path_hits':[],'human_floor_path_hits':[],'adversarial_floor_path_hits':[],'supply_chain_path_hits':[],'governance_change':False,'matrix_human_review_required':False,'floor_human_review_required':False,'human_review_required':False,'floor_reasons':[]}
        r['authority']['required_level']='L1';r['authority']['achieved_level']='L1';r['review_state']='L1_REVIEWED'
        self.assertTrue(any('sensor-derived floor L2' in x for x in semantic_errors(r)))
    def test_failed_sensor_invariant_requires_adversarial(self):
        r=copy.deepcopy(self.base)
        r['sensor_context']['failed_invariants']=['apply-opcodes-reconstruct-target']
        r['risk']['model_assessment']={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
        r['risk']['harness']={'governance_path_hits':[],'human_floor_path_hits':[],'adversarial_floor_path_hits':[],'supply_chain_path_hits':[],'governance_change':False,'matrix_human_review_required':False,'floor_human_review_required':False,'human_review_required':False,'floor_reasons':[]}
        r['authority']['required_level']='L2';r['authority']['achieved_level']='L2';r['review_state']='L2_REVIEWED'
        self.assertTrue(any('sensor-derived floor ADVERSARIAL' in x for x in semantic_errors(r)))
