from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
sys.path.insert(0,str(TOOLS))

from case_ledger import append_event,default_anchor_path
from human_decision_attestation import create as create_human_attestation
from runtime_attestation import create as create_runtime_attestation
from mutation_receipt import capture as capture_mutation_receipt,finalize as finalize_mutation_receipt,reject_output_collision,validate_receipt


class V27ReleaseInvariantTests(unittest.TestCase):
    def test_package_version_is_27(self):
        self.assertEqual((ROOT/'PACKAGE_VERSION').read_text(encoding='utf-8').strip(),'2.7')

    def test_workflow_targets_v27_branch(self):
        text=(ROOT/'.github/workflows/harness-validation.yml').read_text(encoding='utf-8')
        self.assertIn('hardening/v2.7',text)
        self.assertNotIn('refs/heads/hardening/v2.6',text)

    def test_latest_head_review_rule_is_repository_default(self):
        text=(ROOT/'AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('Always review the latest committed code',text)
        self.assertIn('post-fix latest HEAD',text)
        self.assertIn('previous conclusion is **STALE**',text)

    def test_v27_policy_documents_are_versioned(self):
        for name in ('escalation-policy.yml','protected-paths.yml','reviewer-routing.yml','sensor-policy.yml'):
            first=(ROOT/'policy'/name).read_text(encoding='utf-8').splitlines()[0]
            self.assertEqual(first,"schema_version: '2.7'",name)

    def test_mutation_receipt_is_digest_only_and_detects_change(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);secret=root/'sid-bearing.raw';secret.write_text('sensitive-original\n',encoding='utf-8')
            spec=root/'spec.json';spec.write_text(json.dumps({'artifacts':[{'name':'successful-capture','path':str(secret)}]}),encoding='utf-8')
            pre=capture_mutation_receipt(spec);pre_path=root/'pre.json';pre_path.write_text(json.dumps(pre),encoding='utf-8')
            same=finalize_mutation_receipt(pre_path,spec)
            schema=json.loads((ROOT/'schemas/mutation-receipt.schema.json').read_text(encoding='utf-8'))
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(same)),[])
            self.assertTrue(same['all_unchanged']);self.assertEqual(same['authority_effect'],'NONE');self.assertEqual(same['pre_snapshot_digest'],pre['snapshot_digest']);self.assertEqual(validate_receipt(same),[])
            tampered=json.loads(json.dumps(same));tampered['items'][0]['post_sha256']='0'*64
            self.assertTrue(validate_receipt(tampered))
            serialized=json.dumps(same)
            self.assertNotIn(str(secret),serialized);self.assertNotIn('sensitive-original',serialized);self.assertNotIn('"path"',serialized)
            secret.write_text('mutated\n',encoding='utf-8')
            changed=finalize_mutation_receipt(pre_path,spec)
            self.assertFalse(changed['all_unchanged']);self.assertFalse(changed['items'][0]['equal'])
            with self.assertRaises(SystemExit):reject_output_collision(secret,spec)
            with self.assertRaises(SystemExit):reject_output_collision(pre_path,spec,pre_path)

    def test_v27_integrity_artifacts_emit_current_schema(self):
        key='k'
        human=create_human_attestation('CASE','owner','CONFIRMED','a'*40,key,'b'*64,'c'*64)
        self.assertEqual(human['schema_version'],'2.7')
        with tempfile.TemporaryDirectory() as td:
            runtime=create_runtime_attestation(td,key,case_id='CASE',base_sha='a'*40,head_sha='b'*40,l2_fresh_session=True,adversarial_fresh_session=True)
            self.assertEqual(runtime['schema_version'],'2.7')
            ledger=Path(td)/'case-events.jsonl';append_event(ledger,'CASE','CASE_OPENED',{})
            anchor=json.loads(default_anchor_path(ledger).read_text(encoding='utf-8'))
            self.assertEqual(anchor['schema_version'],'2.7')


if __name__=='__main__':
    unittest.main()
