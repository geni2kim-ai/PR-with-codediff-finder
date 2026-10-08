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
from verify_manifest import filesystem_errors
from source_package_receipt import create as create_package_receipt,validate as validate_package_receipt


class V27ReleaseInvariantTests(unittest.TestCase):
    def test_package_version_is_27(self):
        self.assertEqual((ROOT/'PACKAGE_VERSION').read_text(encoding='utf-8').strip(),'2.7')

    def test_workflow_targets_v27_branch(self):
        text=(ROOT/'.github/workflows/harness-validation.yml').read_text(encoding='utf-8')
        self.assertIn('hardening/v2.7',text)
        self.assertNotIn('refs/heads/hardening/v2.6',text)
        self.assertIn('Build validated v2.7 source package',text)
        self.assertIn('Verify clean-extracted v2.7 package',text)
        self.assertIn('source_package_receipt.py create',text)
        self.assertIn('v2.7-source-package',text)
        self.assertGreaterEqual(text.count("github.event_name != 'push' || github.ref != 'refs/heads/hardening/v2.7'"),3)

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
            leaked=json.loads(json.dumps(same));leaked['path']=str(secret);leaked['receipt_digest']='';leaked['receipt_digest']=__import__('common').object_digest(leaked,'receipt_digest')
            self.assertIn('mutation receipt fields mismatch',validate_receipt(leaked))
            serialized=json.dumps(same)
            self.assertNotIn(str(secret),serialized);self.assertNotIn('sensitive-original',serialized);self.assertNotIn('"path"',serialized)
            secret.write_text('mutated\n',encoding='utf-8')
            changed=finalize_mutation_receipt(pre_path,spec)
            self.assertFalse(changed['all_unchanged']);self.assertFalse(changed['items'][0]['equal'])
            with self.assertRaises(SystemExit):reject_output_collision(secret,spec)
            with self.assertRaises(SystemExit):reject_output_collision(pre_path,spec,pre_path)

    def test_extracted_package_manifest_verification_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'sub').mkdir();(root/'a.txt').write_text('alpha\n',encoding='utf-8');(root/'sub'/'b.txt').write_bytes(b'beta\n')
            import hashlib
            rows=[
                f"{hashlib.sha256((root/'a.txt').read_bytes()).hexdigest()}  ./a.txt",
                f"{hashlib.sha256((root/'sub'/'b.txt').read_bytes()).hexdigest()}  ./sub/b.txt",
            ]
            (root/'MANIFEST.sha256').write_text('\n'.join(rows)+'\n',encoding='utf-8')
            self.assertEqual(filesystem_errors(filesystem_root=root)[0],[])
            (root/'a.txt').write_text('tampered\n',encoding='utf-8')
            self.assertTrue(any('package hash mismatch: ./a.txt' in x for x in filesystem_errors(filesystem_root=root)[0]))
            (root/'a.txt').write_text('alpha\n',encoding='utf-8');(root/'extra.txt').write_text('extra\n',encoding='utf-8')
            self.assertTrue(any('unmanifested package file: extra.txt' in x for x in filesystem_errors(filesystem_root=root)[0]))
            (root/'extra.txt').unlink();(root/'sub'/'b.txt').unlink()
            self.assertTrue(any('manifested package file missing: sub/b.txt' in x for x in filesystem_errors(filesystem_root=root)[0]))
            (root/'MANIFEST.sha256').write_text(f"{hashlib.sha256(payload).hexdigest()}  ../a.txt\n",encoding='utf-8')
            with self.assertRaises(ValueError):filesystem_errors(filesystem_root=root)
            (root/'MANIFEST.sha256').write_text(f"{hashlib.sha256(payload).hexdigest()}  .\\a.txt\n",encoding='utf-8')
            with self.assertRaises(ValueError):filesystem_errors(filesystem_root=root)
            outside=root.parent/'outside-manifest.sha256';outside.write_text(f"{hashlib.sha256(payload).hexdigest()}  ./a.txt\n",encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'inside filesystem root'):filesystem_errors(manifest=outside,filesystem_root=root)

    def test_source_package_receipt_binds_zip_manifest_and_head(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pkg=root/'pkg.zip';pkg.write_bytes(b'zip-bytes')
            import hashlib
            payload=b'alpha\n';(root/'a.txt').write_bytes(payload)
            manifest=root/'MANIFEST.sha256';manifest.write_text(f"{hashlib.sha256(payload).hexdigest()}  ./a.txt\n",encoding='utf-8')
            receipt=create_package_receipt(pkg,manifest,'a'*40,clean_extract_verified=True,canonical_validation_passed=True)
            schema=json.loads((ROOT/'schemas/source-package-receipt.schema.json').read_text(encoding='utf-8'))
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(receipt)),[])
            self.assertEqual(validate_package_receipt(receipt,pkg,manifest),[])
            pkg.write_bytes(b'tampered')
            self.assertIn('source package sha256 mismatch',validate_package_receipt(receipt,pkg,manifest))
            pkg.write_bytes(b'zip-bytes');leaked=json.loads(json.dumps(receipt));leaked['path']='secret';leaked['receipt_digest']=''
            leaked['receipt_digest']=__import__('common').object_digest(leaked,'receipt_digest')
            self.assertIn('source package receipt fields mismatch',validate_package_receipt(leaked,pkg,manifest))
            bad_name=json.loads(json.dumps(receipt));bad_name['package_name']='..\\pkg.zip';bad_name['receipt_digest']=''
            bad_name['receipt_digest']=__import__('common').object_digest(bad_name,'receipt_digest')
            self.assertIn('source package receipt package_name invalid',validate_package_receipt(bad_name))
            bad_count=json.loads(json.dumps(receipt));bad_count['manifest_entries']=True;bad_count['receipt_digest']=''
            bad_count['receipt_digest']=__import__('common').object_digest(bad_count,'receipt_digest')
            self.assertIn('source package receipt manifest_entries invalid',validate_package_receipt(bad_count))

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
