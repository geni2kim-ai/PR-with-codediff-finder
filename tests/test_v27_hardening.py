from __future__ import annotations
import json,os,subprocess,sys,tempfile,unittest,zipfile
from unittest import mock
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
sys.path.insert(0,str(TOOLS))

import case_ledger
from case_ledger import append_event,default_anchor_path
from human_decision_attestation import create as create_human_attestation
from runtime_attestation import create as create_runtime_attestation
from mutation_receipt import capture as capture_mutation_receipt,finalize as finalize_mutation_receipt,reject_output_collision,validate_receipt
from verify_manifest import filesystem_errors
from source_package_receipt import create as create_package_receipt,validate as validate_package_receipt
from verify_package_hygiene import generated_paths
from build_source_package import build as build_source_package
from run_review_cycle import disagreement,material_finding_key,material_finding_signature
from common import canonical_finding_path,object_digest
from validate_stage_result import semantic_errors as stage_semantic_errors
from sanitize_review_text import scan_stage_result
from calibration_report import material_agrees
from route_case import reasons_for
from validate_case_record import semantic_errors as case_semantic_errors


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
            legacy=json.loads(json.dumps(receipt))
            for k in ('validation_run_id','validation_run_attempt','validation_workflow_ref'):legacy.pop(k,None)
            legacy['receipt_digest']='';legacy['receipt_digest']=__import__('common').object_digest(legacy,'receipt_digest')
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(legacy)),[])
            self.assertEqual(validate_package_receipt(legacy,pkg,manifest),[])
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

    def test_source_package_receipt_can_bind_ci_validation_run(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);package=root/'pkg.zip';package.write_bytes(b'zip-bytes')
            manifest=root/'MANIFEST.sha256';payload=root/'file.txt';payload.write_text('x',encoding='utf-8')
            manifest.write_text(__import__('hashlib').sha256(payload.read_bytes()).hexdigest()+'  ./file.txt\n',encoding='utf-8')
            receipt=create_package_receipt(package,manifest,'a'*40,clean_extract_verified=True,canonical_validation_passed=True,
                                           validation_run_id=12345,validation_run_attempt=2,validation_workflow_ref='owner/repo/.github/workflows/harness-validation.yml@refs/pull/5/merge')
            self.assertEqual(receipt['validation_run_id'],12345);self.assertEqual(receipt['validation_run_attempt'],2)
            self.assertEqual(validate_package_receipt(receipt,package,manifest),[])
            tampered=json.loads(json.dumps(receipt));tampered['validation_run_id']=999;tampered['receipt_digest']=''
            tampered['receipt_digest']=__import__('common').object_digest(tampered,'receipt_digest')
            self.assertEqual(tampered['validation_run_id'],999)
            # The digest binds run metadata, while external GitHub artifact/run
            # metadata remains the authority for whether that run actually existed.
            self.assertEqual(validate_package_receipt(tampered,package,manifest),[])

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

    def test_material_agreement_preserves_severity_and_duplicate_multiplicity(self):
        def finding(severity='major'):
            return {'severity':severity,'failure_family':'SECURITY-CRITICAL','axis':'correctness_security','path':'src/a.py'}
        one={'verdict':'FINDINGS','findings':[finding()]}
        two={'verdict':'FINDINGS','findings':[finding(),finding()]}
        minor={'verdict':'FINDINGS','findings':[finding('minor')]}
        self.assertTrue(disagreement(one,two,changed_paths=['src/a.py']))
        self.assertTrue(disagreement(one,minor,changed_paths=['src/a.py']))
        self.assertEqual(material_finding_key(finding()),material_finding_key(finding('minor')))
        self.assertNotEqual(material_finding_signature(finding()),material_finding_signature(finding('minor')))

    def test_calibration_and_route_use_persisted_material_signatures(self):
        key=material_finding_key({'severity':'major','failure_family':'SECURITY-CRITICAL','axis':'correctness_security','path':'src/a.py'})
        l1={'level':'L1','verdict':'FINDINGS','confidence':'high','material_finding_count':1,'material_finding_keys':[key],
            'material_finding_signatures':['major|'+key]}
        l2={'level':'L2','verdict':'FINDINGS','confidence':'high','material_finding_count':1,'material_finding_keys':[key],
            'material_finding_signatures':['minor|'+key]}
        self.assertFalse(material_agrees(l1,l2))
        self.assertIn('L1_L2_DISAGREEMENT',reasons_for({'review_trail':[l1,l2],'labels':[],'failure_families':[]}))

        # Mixed old/new rows compare at the best identity level both possess.
        legacy_same=dict(l1);legacy_same.pop('material_finding_signatures')
        self.assertTrue(material_agrees(l1,legacy_same))
        self.assertNotIn('L1_L2_DISAGREEMENT',reasons_for({'review_trail':[l1,dict(legacy_same,level='L2')],'labels':[],'failure_families':[]}))

        # Pre-signature v2.7 records cannot recover severity mapping, but count
        # still prevents a two-vs-one same-key omission from becoming agreement.
        old_two=dict(l1);old_two.pop('material_finding_signatures');old_two['material_finding_count']=2
        old_one=dict(l2);old_one.pop('material_finding_signatures');old_one['material_finding_count']=1
        self.assertFalse(material_agrees(old_two,old_one))

    def test_case_record_rejects_inconsistent_material_signatures(self):
        key='finding:'+'a'*24
        row={'review_id':'R1','parent_review_id':None,'level':'L1','model':{'family':'mock','version':'1'},'reviewed_head_sha':'b'*40,
             'evidence_digest':'c'*64,'achieved_level':'L1','requested_level':'L1','independent_context':False,
             'material_finding_count':2,'material_finding_keys':[key],'material_finding_signatures':['major|'+key],
             'major_finding_count':1,'blocker_finding_count':0}
        case={'binding':{'head_sha':'b'*40},'sensor':{'evidence_digest':'c'*64},'review_trail':[row],'labels':[]}
        errs=case_semantic_errors(case)
        self.assertTrue(any('material_finding_signatures count mismatch' in x for x in errs),errs)

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
        literal_host_like=r'C:\\literal.py'
        self.assertEqual(canonical_finding_path(literal_host_like,[literal_host_like]),literal_host_like)

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
        unsafe_even_if_listed=self._stage_path_errors('../src/a.py',changed_paths=['../src/a.py'])
        self.assertTrue(any('path invalid' in x for x in unsafe_even_if_listed),unsafe_even_if_listed)
        wrong_separator=self._stage_path_errors(r'src\\a.py',changed_paths=['src/a.py'])
        self.assertTrue(any('outside changed_paths' in x for x in wrong_separator),wrong_separator)


    def test_hmac_history_downgrade_is_rejected_by_witness_key_id_and_external_expectation(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger);key='ledger-key'
            append_event(ledger,'CASE','CASE_OPENED',{},hmac_key=key,key_id='key-v1')
            events=case_ledger.load_events(ledger)

            forged=json.loads(anchor.read_text(encoding='utf-8'));forged['hmac_sha256']=None
            anchor.write_text(json.dumps(forged),encoding='utf-8')
            errs=case_ledger.validate_anchor(ledger,anchor,events,'CASE')
            self.assertTrue(any('HMAC' in x for x in errs),errs)

            case_ledger.canonical_auth_witness_path(ledger).unlink()
            errs=case_ledger.validate_anchor(ledger,anchor,events,'CASE')
            self.assertTrue(any('HMAC' in x for x in errs),errs)

            forged['key_id']=None;anchor.write_text(json.dumps(forged),encoding='utf-8')
            with mock.patch.dict(os.environ,{'MAESTRO_LEDGER_EXPECT_KEY_ID':'key-v1'},clear=False):
                errs=case_ledger.validate_anchor(ledger,anchor,events,'CASE')
            self.assertTrue(any('key_id mismatch' in x for x in errs),errs)
            self.assertTrue(any('HMAC key unavailable' in x for x in errs),errs)

    def test_signed_append_journal_cannot_be_downgraded_to_unsigned(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger);key='ledger-key';txp=case_ledger.pending_append_path(ledger)
            original=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    append_event(ledger,'CASE','CASE_OPENED',{'v':1},hmac_key=key,key_id='key-v1',event_instance_id='req-1')
            finally:
                case_ledger.write_anchor=original
            case_ledger.canonical_auth_witness_path(ledger).unlink()
            tx=json.loads(txp.read_text(encoding='utf-8'));tx['hmac_sha256']=None
            txp.write_text(json.dumps(tx),encoding='utf-8')
            with self.assertRaisesRegex(case_ledger.LedgerRecoveryError,'HMAC key unavailable'):
                case_ledger.recover_pending_append_if_present(ledger,anchor)

            tx['key_id']=None;tx['transaction_digest']=case_ledger._append_tx_digest(tx)
            txp.write_text(json.dumps(tx),encoding='utf-8')
            with mock.patch.dict(os.environ,{'MAESTRO_LEDGER_EXPECT_KEY_ID':'key-v1'},clear=False):
                with self.assertRaisesRegex(case_ledger.LedgerRecoveryError,'key_id mismatch|HMAC key unavailable'):
                    case_ledger.recover_pending_append_if_present(ledger,anchor)

    def test_pending_append_repairs_exact_torn_event_tail(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            original=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    append_event(ledger,'CASE','CASE_OPENED',{'v':1},event_instance_id='req-torn')
            finally:
                case_ledger.write_anchor=original
            raw=ledger.read_bytes();self.assertGreater(len(raw),20)
            ledger.write_bytes(raw[:len(raw)//2])
            self.assertTrue(case_ledger.recover_pending_append_if_present(ledger,anchor))
            events=case_ledger.load_events(ledger)
            self.assertEqual(len(events),1)
            self.assertFalse(case_ledger.validate_events(events,'CASE'))
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,events,'CASE'))

    def test_unmatched_torn_tail_raises_typed_recovery_error(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            original=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    append_event(ledger,'CASE','CASE_OPENED',{'v':1},event_instance_id='req-bad-torn')
            finally:
                case_ledger.write_anchor=original
            raw=ledger.read_bytes();ledger.write_bytes(raw[:max(1,len(raw)//2)]+b'X')
            with self.assertRaises(case_ledger.LedgerTornWriteError):
                case_ledger.recover_pending_append_if_present(ledger,anchor)

    def test_recovery_distinguishes_intentional_duplicate_from_same_request_retry(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            original=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    append_event(ledger,'CASE','CASE_OPENED',{'v':1})
            finally:
                case_ledger.write_anchor=original
            second=append_event(ledger,'CASE','CASE_OPENED',{'v':1})
            self.assertEqual(second['seq'],2)
            self.assertEqual(len(case_ledger.load_events(ledger)),2)

        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            original=case_ledger.write_anchor
            case_ledger.write_anchor=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('anchor crash'))
            try:
                with self.assertRaises(RuntimeError):
                    append_event(ledger,'CASE','CASE_OPENED',{'v':1},event_instance_id='stable-request')
            finally:
                case_ledger.write_anchor=original
            recovered=append_event(ledger,'CASE','CASE_OPENED',{'v':1},event_instance_id='stable-request')
            self.assertEqual(recovered['seq'],1)
            self.assertEqual(len(case_ledger.load_events(ledger)),1)


    def test_recovered_event_instance_collision_rejects_conflicting_requests(self):
        # A retry token must not cause a changed payload/type/case/timestamp
        # to be mistaken for an already-applied logical request.
        collisions=[
            ('CASE','CASE_OPENED',{'v':2},None),
            ('CASE','SENSOR_ACCEPTED',{'v':1},None),
            ('OTHER','CASE_OPENED',{'v':1},None),
            ('CASE','CASE_OPENED',{'v':1},'2026-01-01T00:00:00Z'),
        ]
        for requested_case,kind,payload,stamp in collisions:
            with self.subTest(case=requested_case,kind=kind,payload=payload,timestamp=stamp):
                with tempfile.TemporaryDirectory() as td:
                    ledger=Path(td)/'case-events.jsonl'
                    with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('anchor crash')):
                        with self.assertRaisesRegex(RuntimeError,'anchor crash'):
                            append_event(ledger,'CASE','CASE_OPENED',{'v':1},event_instance_id='stable-id')
                    self.assertTrue(case_ledger.pending_append_path(ledger).exists())
                    if requested_case!='CASE':
                        # The earlier sticky case-ID witness is the correct
                        # first fail-closed boundary; recovery must not run.
                        with self.assertRaisesRegex(ValueError,'auth witness case_id mismatch'):
                            append_event(ledger,requested_case,kind,payload,
                                         timestamp=stamp,event_instance_id='stable-id')
                        self.assertTrue(case_ledger.pending_append_path(ledger).exists())
                        self.assertFalse(default_anchor_path(ledger).exists())
                        continue
                    with self.assertRaises(case_ledger.LedgerRecoveryError) as ctx:
                        append_event(ledger,requested_case,kind,payload,
                                     timestamp=stamp,event_instance_id='stable-id')
                    self.assertEqual(ctx.exception.code,'EVENT_INSTANCE_CONFLICT')
                    events=case_ledger.load_events(ledger)
                    self.assertEqual(len(events),1)
                    self.assertEqual(events[0]['payload'],{'v':1})
                    self.assertFalse(case_ledger.validate_events(events,'CASE'))
                    self.assertFalse(case_ledger.validate_anchor(ledger,default_anchor_path(ledger),events,'CASE'))
                    self.assertFalse(case_ledger.pending_append_path(ledger).exists())


    def test_failed_unsigned_to_signed_upgrade_preserves_existing_witness(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{'v':1},event_instance_id='first')
            witness_path=case_ledger.canonical_auth_witness_path(ledger)
            old_witness=witness_path.read_bytes()
            old_anchor=anchor.read_bytes()
            with self.assertRaisesRegex(ValueError,'explicit HMAC migration'):
                append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                             hmac_key='new-key',key_id='key-v1',event_instance_id='second')
            self.assertEqual(witness_path.read_bytes(),old_witness)
            self.assertEqual(anchor.read_bytes(),old_anchor)
            self.assertFalse(case_ledger.load_auth_witness(ledger,'CASE')['hmac_required'])
            appended=append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':3},event_instance_id='third')
            self.assertEqual(appended['seq'],2)
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,case_ledger.load_events(ledger),'CASE'))

    def test_unsigned_pending_cannot_poison_witness_on_signed_retry(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{'v':1},event_instance_id='first')
            witness_path=case_ledger.canonical_auth_witness_path(ledger)
            original_witness=witness_path.read_bytes()
            with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('anchor crash')):
                with self.assertRaisesRegex(RuntimeError,'anchor crash'):
                    append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='pending-2')
            with self.assertRaisesRegex(case_ledger.LedgerRecoveryError,'HMAC missing'):
                append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='pending-2',
                             hmac_key='new-key',key_id='key-v1')
            self.assertEqual(witness_path.read_bytes(),original_witness)
            self.assertTrue(case_ledger.pending_append_path(ledger).exists())
            recovered=append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='pending-2')
            self.assertEqual(recovered['seq'],2)
            self.assertFalse(case_ledger.pending_append_path(ledger).exists())
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,case_ledger.load_events(ledger),'CASE'))

    def test_untrusted_signed_pending_does_not_create_sticky_witness(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger);key='ledger-key'
            with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('anchor crash')):
                with self.assertRaisesRegex(RuntimeError,'anchor crash'):
                    append_event(ledger,'CASE','CASE_OPENED',{'v':1},
                                 hmac_key=key,key_id='key-v1',event_instance_id='signed-1')
            witness_path=case_ledger.canonical_auth_witness_path(ledger)
            witness_path.unlink()  # legacy/missing witness; journal must prove its own MAC
            tx_path=case_ledger.pending_append_path(ledger)
            signed_bytes=tx_path.read_bytes()
            bad=json.loads(signed_bytes)
            bad['hmac_sha256']='0'*64
            tx_path.write_text(json.dumps(bad),encoding='utf-8')
            with self.assertRaisesRegex(case_ledger.LedgerRecoveryError,'HMAC mismatch'):
                append_event(ledger,'CASE','CASE_OPENED',{'v':1},
                             hmac_key=key,key_id='key-v1',event_instance_id='signed-1')
            self.assertFalse(witness_path.exists())
            tx_path.write_bytes(signed_bytes)
            recovered=append_event(ledger,'CASE','CASE_OPENED',{'v':1},
                                   hmac_key=key,key_id='key-v1',event_instance_id='signed-1')
            self.assertEqual(recovered['seq'],1)
            self.assertTrue(case_ledger.load_auth_witness(ledger,'CASE')['hmac_required'])
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,case_ledger.load_events(ledger),'CASE',key,True))

    def test_preexisting_anchorless_ledger_does_not_create_witness(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';ledger.write_text('',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'existing ledger anchor missing'):
                append_event(ledger,'CASE','CASE_OPENED',{},hmac_key='key',key_id='key-v1')
            self.assertFalse(case_ledger.canonical_auth_witness_path(ledger).exists())


    def test_forged_hmac_marker_does_not_poison_unsigned_history(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{'v':1})
            original_anchor=anchor.read_bytes()
            witness=case_ledger.canonical_auth_witness_path(ledger)
            original_witness=witness.read_bytes()
            forged=json.loads(original_anchor);forged['key_id']='key-v1';forged['hmac_sha256']='0'*64
            anchor.write_text(json.dumps(forged),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'HMAC mismatch'):
                append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                             hmac_key='real-key',key_id='key-v1')
            self.assertEqual(witness.read_bytes(),original_witness)
            anchor.write_bytes(original_anchor)
            ev=append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':3})
            self.assertEqual(ev['seq'],2)
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,case_ledger.load_events(ledger),'CASE'))

    def test_signed_anchor_key_id_change_cannot_poison_missing_witness(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            key='ledger-key'
            append_event(ledger,'CASE','CASE_OPENED',{'v':1},hmac_key=key,key_id='old-key')
            witness=case_ledger.canonical_auth_witness_path(ledger)
            witness.unlink();original=anchor.read_bytes()
            with self.assertRaisesRegex(ValueError,'key_id change requires explicit migration'):
                append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                             hmac_key=key,key_id='new-key')
            self.assertFalse(witness.exists());self.assertEqual(anchor.read_bytes(),original)
            ev=append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':3},
                            hmac_key=key,key_id='old-key')
            self.assertEqual(ev['seq'],2)
            self.assertEqual(case_ledger.load_auth_witness(ledger,'CASE')['key_id'],'old-key')
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,case_ledger.load_events(ledger),'CASE',key,True))

    def test_unsigned_pending_with_forged_hmac_anchor_keeps_witness(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{'v':1})
            old_anchor=anchor.read_bytes()
            witness=case_ledger.canonical_auth_witness_path(ledger);old_witness=witness.read_bytes()
            with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('crash')):
                with self.assertRaisesRegex(RuntimeError,'crash'):
                    append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='req-2')
            forged=json.loads(old_anchor);forged['key_id']='key-v1';forged['hmac_sha256']='0'*64
            anchor.write_text(json.dumps(forged),encoding='utf-8')
            with self.assertRaisesRegex(case_ledger.LedgerRecoveryError,'HMAC missing'):
                append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='req-2',
                             hmac_key='real-key',key_id='key-v1')
            self.assertEqual(witness.read_bytes(),old_witness)
            self.assertTrue(case_ledger.pending_append_path(ledger).exists())
            anchor.write_bytes(old_anchor)
            recovered=append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='req-2')
            self.assertEqual(recovered['seq'],2)
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,case_ledger.load_events(ledger),'CASE'))

    def test_invalid_new_event_cannot_mutate_ledger_or_witness(self):
        invalid=[('CASE','UNRECOGNIZED_EVENT',{'v':1}),('BAD/CASE','CASE_OPENED',{'v':1}),
                 ('CASE','CASE_OPENED',['not-an-object']),('CASE','CASE_OPENED',{'nonjson':{1,2}})]
        for cid,kind,payload in invalid:
            with self.subTest(cid=cid,kind=kind,payload=str(payload)):
                with tempfile.TemporaryDirectory() as td:
                    ledger=Path(td)/'case-events.jsonl'
                    with self.assertRaises(ValueError):append_event(ledger,cid,kind,payload)
                    for path in (ledger,default_anchor_path(ledger),
                                 case_ledger.canonical_auth_witness_path(ledger),
                                 case_ledger.pending_append_path(ledger)):
                        self.assertFalse(path.exists(),path)
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{'v':1})
            orig_anchor=anchor.read_bytes()
            witness=case_ledger.canonical_auth_witness_path(ledger);orig_witness=witness.read_bytes()
            with self.assertRaisesRegex(ValueError,'invalid event input'):
                append_event(ledger,'CASE','UNRECOGNIZED_EVENT',{'v':2})
            self.assertEqual(len(case_ledger.load_events(ledger)),1)
            self.assertEqual(anchor.read_bytes(),orig_anchor)
            self.assertEqual(witness.read_bytes(),orig_witness)


    def test_pending_recovery_preserves_corrupted_signed_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger);key='key-secret'
            append_event(ledger,'CASE','CASE_OPENED',{'v':1},hmac_key=key,key_id='kid')
            valid_anchor=anchor.read_bytes()
            with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('crash')):
                with self.assertRaisesRegex(RuntimeError,'crash'):
                    append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                                 hmac_key=key,key_id='kid',event_instance_id='two')
            tx=case_ledger.pending_append_path(ledger)
            ledger_bytes=ledger.read_bytes();tx_bytes=tx.read_bytes()
            bad=json.loads(valid_anchor);bad['hmac_sha256']='0'*64
            anchor.write_text(json.dumps(bad),encoding='utf-8');bad_bytes=anchor.read_bytes()
            with self.assertRaises(case_ledger.LedgerRecoveryError) as cm:
                case_ledger.recover_pending_append_if_present(ledger,hmac_key=key)
            self.assertEqual(cm.exception.code,'APPEND_ANCHOR_INVALID')
            self.assertIn('HMAC mismatch',str(cm.exception))
            self.assertEqual(ledger.read_bytes(),ledger_bytes)
            self.assertEqual(anchor.read_bytes(),bad_bytes)
            self.assertEqual(tx.read_bytes(),tx_bytes)
            anchor.write_bytes(valid_anchor)
            self.assertTrue(case_ledger.recover_pending_append_if_present(ledger,hmac_key=key))
            self.assertFalse(tx.exists())
            ev=case_ledger.load_events(ledger)
            self.assertEqual(len(ev),2)
            self.assertFalse(case_ledger.validate_anchor(ledger,anchor,ev,'CASE',key,True))

    def test_pending_recovery_does_not_recreate_deleted_prior_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{'v':1})
            saved=anchor.read_bytes()
            with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('crash')):
                with self.assertRaisesRegex(RuntimeError,'crash'):
                    append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='two')
            tx=case_ledger.pending_append_path(ledger);old_tx=tx.read_bytes();old_ledger=ledger.read_bytes()
            anchor.unlink()
            with self.assertRaises(case_ledger.LedgerRecoveryError) as cm:
                case_ledger.recover_pending_append_if_present(ledger)
            self.assertEqual(cm.exception.code,'APPEND_ANCHOR_INVALID')
            self.assertEqual(tx.read_bytes(),old_tx)
            self.assertEqual(ledger.read_bytes(),old_ledger)
            self.assertFalse(anchor.exists())
            anchor.write_bytes(saved)
            self.assertTrue(case_ledger.recover_pending_append_if_present(ledger))
            self.assertEqual(len(case_ledger.load_events(ledger)),2)

    def test_pending_recovery_accepts_committed_anchor_before_journal_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger);key='key-secret'
            append_event(ledger,'CASE','CASE_OPENED',{'v':1},hmac_key=key,key_id='kid')
            tx=case_ledger.pending_append_path(ledger);original_unlink=Path.unlink
            def crash_on_tx(path,*args,**kwargs):
                if path==tx:raise RuntimeError('after anchor crash')
                return original_unlink(path,*args,**kwargs)
            with mock.patch.object(Path,'unlink',crash_on_tx):
                with self.assertRaisesRegex(RuntimeError,'after anchor crash'):
                    append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                                 hmac_key=key,key_id='kid',event_instance_id='two')
            self.assertTrue(tx.exists());anchor_before=anchor.read_bytes()
            same=append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                              hmac_key=key,key_id='kid',event_instance_id='two')
            self.assertEqual(same['seq'],2)
            self.assertFalse(tx.exists())
            self.assertEqual(len(case_ledger.load_events(ledger)),2)
            self.assertEqual(anchor.read_bytes(),anchor_before)

    def test_invalid_pending_event_schema_fails_before_replay(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{'v':1})
            prior=ledger.read_bytes();old_anchor=anchor.read_bytes()
            with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('crash')):
                with self.assertRaisesRegex(RuntimeError,'crash'):
                    append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},event_instance_id='two')
            tx_path=case_ledger.pending_append_path(ledger)
            tx=json.loads(tx_path.read_text(encoding='utf-8'))
            ledger.write_bytes(prior)
            tx['event']['event_type']='INVALID_EVENT'
            tx['event']['event_hash']=object_digest(tx['event'],'event_hash')
            tx['transaction_digest']=case_ledger._append_tx_digest(tx)
            tx_path.write_text(json.dumps(tx),encoding='utf-8')
            dirty=tx_path.read_bytes()
            with self.assertRaisesRegex(case_ledger.LedgerRecoveryError,'event schema'):
                case_ledger.recover_pending_append_if_present(ledger)
            self.assertEqual(ledger.read_bytes(),prior)
            self.assertEqual(anchor.read_bytes(),old_anchor)
            self.assertEqual(tx_path.read_bytes(),dirty)


    def test_append_retry_with_missing_witness_rejects_forged_prior_anchor_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger);key='key-secret'
            append_event(ledger,'CASE','CASE_OPENED',{'v':1},hmac_key=key,key_id='kid')
            old_anchor=anchor.read_bytes()
            with mock.patch.object(case_ledger,'write_anchor',side_effect=RuntimeError('crash')):
                with self.assertRaisesRegex(RuntimeError,'crash'):
                    append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                                 hmac_key=key,key_id='kid',event_instance_id='two')
            tx=case_ledger.pending_append_path(ledger)
            tx_bytes=tx.read_bytes();ledger_bytes=ledger.read_bytes()
            witness=case_ledger.canonical_auth_witness_path(ledger)
            witness.unlink()
            bad=json.loads(old_anchor);bad['hmac_sha256']='0'*64
            anchor.write_text(json.dumps(bad),encoding='utf-8')
            bad_anchor=anchor.read_bytes()
            with self.assertRaises(case_ledger.LedgerRecoveryError) as ctx:
                append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                             hmac_key=key,key_id='kid',event_instance_id='two')
            self.assertEqual(ctx.exception.code,'APPEND_ANCHOR_INVALID')
            self.assertFalse(witness.exists())
            self.assertEqual(anchor.read_bytes(),bad_anchor)
            self.assertEqual(ledger.read_bytes(),ledger_bytes)
            self.assertEqual(tx.read_bytes(),tx_bytes)
            anchor.write_bytes(old_anchor)
            recovered=append_event(ledger,'CASE','SENSOR_ACCEPTED',{'v':2},
                                   hmac_key=key,key_id='kid',event_instance_id='two')
            self.assertEqual(recovered['seq'],2)
            self.assertTrue(case_ledger.load_auth_witness(ledger,'CASE')['hmac_required'])
            self.assertFalse(tx.exists())


    def test_standalone_validator_rejects_mixed_case_ledger_with_valid_local_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            first=append_event(ledger,'ALPHA','CASE_OPENED',{'v':1})
            second={'schema_version':'2.4','case_id':'BETA','seq':2,
                    'event_type':'SENSOR_ACCEPTED','timestamp':first['timestamp'],
                    'payload':{'v':2},'prev_hash':first['event_hash'],'event_hash':''}
            second['event_hash']=object_digest(second,'event_hash')
            events=[first,second]
            ledger.write_bytes(case_ledger._events_bytes(events))
            case_ledger.write_anchor(ledger,anchor,'ALPHA',events)
            errors=case_ledger.validate_events(case_ledger.load_events(ledger))
            self.assertTrue(any('case_id mismatch at 2' in e for e in errors),errors)
            env={**os.environ}
            env.pop('MAESTRO_LEDGER_HMAC_KEY',None)
            env.pop('MAESTRO_LEDGER_EXPECT_KEY_ID',None)
            cp=subprocess.run([sys.executable,str(TOOLS/'case_ledger.py'),'validate',
                               '--ledger',str(ledger)],capture_output=True,text=True,env=env)
            self.assertNotEqual(cp.returncode,0)
            self.assertIn('case_id mismatch at 2',cp.stdout+cp.stderr)

    def test_anchor_validator_rejects_corrupt_existing_auth_witness(self):
        for signed in (False,True):
            with self.subTest(signed=signed):
                with tempfile.TemporaryDirectory() as td:
                    ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
                    key='signed-secret' if signed else None
                    append_event(ledger,'CASE','CASE_OPENED',{'v':1},
                                 hmac_key=key,key_id='kid' if signed else None)
                    witness=case_ledger.canonical_auth_witness_path(ledger)
                    clean=witness.read_bytes()
                    corrupt=json.loads(clean)
                    corrupt['witness_digest']='0'*64
                    witness.write_text(json.dumps(corrupt),encoding='utf-8')
                    events=case_ledger.load_events(ledger)
                    errors=case_ledger.validate_anchor(ledger,anchor,events,'CASE',key)
                    self.assertTrue(any('auth witness digest mismatch' in e for e in errors),errors)
                    witness.write_bytes(clean)
                    self.assertEqual(case_ledger.validate_anchor(ledger,anchor,events,'CASE',key),[])

    def test_json_nonobject_event_and_anchor_rejected_without_attribute_error(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/'case-events.jsonl';anchor=default_anchor_path(ledger)
            append_event(ledger,'CASE','CASE_OPENED',{})
            ledger.write_text('["not-a-case-event"]',encoding='utf-8')
            events=case_ledger.load_events(ledger)
            errors=case_ledger.validate_events(events)
            self.assertTrue(any('event must be an object at 1' in e for e in errors),errors)
            anchor_errors=case_ledger.validate_anchor(ledger,anchor,events)
            self.assertIn('ledger events malformed for anchor validation',anchor_errors)


if __name__=='__main__':
    unittest.main()
