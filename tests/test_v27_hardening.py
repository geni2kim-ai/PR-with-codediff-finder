from __future__ import annotations
import json,subprocess,sys,tempfile,unittest,zipfile
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
from verify_package_hygiene import generated_paths
from build_source_package import build as build_source_package
from run_review_cycle import disagreement,material_finding_key
from common import canonical_finding_path,object_digest
from validate_stage_result import semantic_errors as stage_semantic_errors
from sanitize_review_text import scan_stage_result


class V27ReleaseInvariantTests(unittest.TestCase):
    def test_package_version_is_27(self):
        self.assertEqual((ROOT/'PACKAGE_VERSION').read_text(encoding='utf-8').strip(),'2.7')

    def test_workflow_targets_v27_branch(self):
        text=(ROOT/'.github/workflows/harness-validation.yml').read_text(encoding='utf-8')
        self.assertIn('hardening/v2.7',text)
        self.assertNotIn('refs/heads/hardening/v2.6',text)
        self.assertIn('Reject tracked generated artifacts',text)
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

    def test_source_package_builder_preserves_exact_git_blob_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            repo=Path(td)/'repo';repo.mkdir()
            def git(*args):
                cp=subprocess.run(['git','-C',str(repo),*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
                self.assertEqual(cp.returncode,0,cp.stderr)
                return cp.stdout.strip()
            git('init','-q');git('config','user.email','test@example.invalid');git('config','user.name','Test')
            raw=b'line1\r\nline2\nline3\r\n'
            (repo/'vendor.txt').write_bytes(raw)
            (repo/'MANIFEST.sha256').write_text(__import__('hashlib').sha256(raw).hexdigest()+'  ./vendor.txt\n',encoding='utf-8')
            git('add','.');git('commit','-qm','fixture')
            out=Path(td)/'pkg.zip'
            self.assertEqual(build_source_package(repo,'HEAD',out,'pkg/'),2)
            with zipfile.ZipFile(out) as zf:
                self.assertEqual(zf.read('pkg/vendor.txt'),raw)
                self.assertEqual(zf.read('pkg/MANIFEST.sha256'),(repo/'MANIFEST.sha256').read_bytes())

    def test_package_hygiene_rejects_generated_cache_artifacts(self):
        bad=generated_paths([
            'src/app.py',
            '.pytest_cache/v/cache/nodeids',
            'pkg/__pycache__/mod.cpython-312.pyc',
            'pkg/tool.pyo',
        ])
        self.assertEqual(bad,[
            '.pytest_cache/v/cache/nodeids',
            'pkg/__pycache__/mod.cpython-312.pyc',
            'pkg/tool.pyo',
        ])
        self.assertEqual(generated_paths(['src/app.py','tests/test_app.py']),[])

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
            payload=b'alpha\n'
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


    def test_disagreement_distinguishes_same_family_axis_on_different_paths(self):
        def review(path):
            return {
                'verdict':'FINDINGS',
                'findings':[{
                    'severity':'major',
                    'failure_family':'CORRECTNESS',
                    'axis':'correctness_security',
                    'path':path,
                }],
            }
        self.assertTrue(disagreement(review('src/a.py'),review('src/b.py')))
        self.assertFalse(disagreement(review('src/a.py'),review('./src/a.py')))
        self.assertTrue(disagreement(review('src/a.py'),review(r'src\\a.py'),changed_paths=['src/a.py',r'src\\a.py']))

    def test_material_finding_identity_preserves_exact_git_backslash_paths(self):
        base={'severity':'major','failure_family':'CORRECTNESS','axis':'correctness_security'}
        slash=dict(base,path='src/module.py')
        dotted=dict(base,path='./src/module.py')
        backslash=dict(base,path=r'src\\module.py')
        self.assertEqual(material_finding_key(slash),material_finding_key(dotted))
        self.assertNotEqual(material_finding_key(slash),material_finding_key(backslash))
        self.assertEqual(canonical_finding_path('./src/module.py',['src/module.py']),'src/module.py')
        self.assertEqual(canonical_finding_path(r'src\\module.py',[r'src\\module.py']),r'src\\module.py')
        with self.assertRaises(ValueError):canonical_finding_path('../src/module.py',['src/module.py'])
        with self.assertRaises(ValueError):canonical_finding_path(r'C:\\repo\\src\\module.py',['src/module.py'])

    def _stage_path_errors(self,path,preexisting=False,activated=False,changed_paths=None):
        contract={'node_id':'node','model':{'family':'mock','version':'1'},'prompt_digest':'a'*64,'skill_digest':'b'*64,'policy_digest':'c'*64,'standards_digest':'d'*64,'worker_command_digest':'e'*64}
        task={'task_id':'TASK','case_id':'CASE','level':'L1','binding':{'repository':'owner/repo','head_sha':'f'*40},'sensor':{'evidence_digest':'1'*64},
              'reviewer_contract':contract,'limits':{'max_findings':12,'max_nits':2},'changed_paths':changed_paths or ['src/a.py']}
        finding={'finding_id':'F-1','severity':'major','path':path,'preexisting':preexisting,'activated_or_worsened':activated}
        result={'task_id':'TASK','case_id':'CASE','level':'L1','binding':{'repository':'owner/repo','reviewed_head_sha':'f'*40},'evidence_digest':'1'*64,
                'reviewer':{**contract,'independent_context':False},'verdict':'FINDINGS','confidence':'high','findings':[finding],'output_safety':{},'result_digest':''}
        result['output_safety']=scan_stage_result(result);result['result_digest']=object_digest(result,'result_digest')
        return stage_semantic_errors(result,task)

    def test_reviewer_finding_path_scope_is_fail_closed_without_blocking_activated_preexisting(self):
        changed=self._stage_path_errors('./src/a.py')
        self.assertFalse(any('path invalid' in x or 'outside changed_paths' in x for x in changed),changed)
        outside=self._stage_path_errors('src/other.py')
        self.assertTrue(any('outside changed_paths' in x for x in outside),outside)
        activated=self._stage_path_errors('src/other.py',preexisting=True,activated=True)
        self.assertFalse(any('path invalid' in x or 'outside changed_paths' in x for x in activated),activated)
        unsafe=self._stage_path_errors('../src/a.py')
        self.assertTrue(any('path invalid' in x for x in unsafe),unsafe)


if __name__=='__main__':
    unittest.main()
