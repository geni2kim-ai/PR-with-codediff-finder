from __future__ import annotations
import argparse, importlib.metadata, importlib.util, json, re, subprocess, sys, time
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from common import object_digest, sha256_file, write_json
from policy_engine import load_yaml, classify_paths, normalize_repo_path

QUALITY_ORDER={"PROVEN_EXACT":0,"HEURISTIC":1,"APPROXIMATE":2,"NOT_APPLICABLE":-1}
ENC_HIGH={"utf-8","utf-8-sig","utf-16"}
# Legacy single-byte/multibyte guesses can decode the wrong charset losslessly. Treat
# them as LOW confidence for a review gate unless a future detector proves charset.
ENC_MED=set()
VENDOR_PARTS={"vendor","vendors","node_modules","third_party","third-party","external"}
GENERATED_PARTS={"generated","gen","dist","build","coverage"}
LANG={
 '.py':'python','.js':'javascript','.jsx':'javascript','.ts':'typescript','.tsx':'typescript',
 '.java':'java','.kt':'kotlin','.kts':'kotlin','.cs':'csharp','.go':'go','.rs':'rust',
 '.c':'c','.h':'c','.cpp':'cpp','.cc':'cpp','.hpp':'cpp','.sql':'sql','.json':'json',
 '.yaml':'yaml','.yml':'yaml','.toml':'toml','.md':'markdown','.sh':'shell','.ps1':'powershell'
}


def run_git(repo:Path,*args:str,check=True)->bytes:
    cp=subprocess.run(['git','-C',str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if check and cp.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.decode('utf-8','replace')[:500]}")
    return cp.stdout


def resolve_commit(repo:Path, ref:str)->str:
    return run_git(repo,'rev-parse','--verify',f'{ref}^{{commit}}').decode().strip()


def merge_base(repo:Path, base_ref:str, head_ref:str)->str:
    return run_git(repo,'merge-base',base_ref,head_ref).decode().strip()


def changed_entries(repo:Path,base:str,head:str):
    raw=run_git(repo,'diff','--name-status','-z','-M','-C',base,head)
    toks=raw.decode('utf-8','surrogateescape').split('\0')
    if toks and toks[-1]=='': toks.pop()
    out=[];i=0
    while i<len(toks):
        status=toks[i]; i+=1
        code=status[0] if status else '?'
        if code in {'R','C'}:
            old=toks[i];new=toks[i+1];i+=2
            out.append((status,normalize_repo_path(old),normalize_repo_path(new)))
        else:
            path=toks[i];i+=1
            out.append((status,None,normalize_repo_path(path)))
    return out


def tree_entry(repo:Path,sha:str,path:str):
    raw=run_git(repo,'ls-tree','-z',sha,'--',path,check=False)
    if not raw:return None
    first=raw.split(b'\0',1)[0]
    try:
        left,_=first.split(b'\t',1);mode,typ,obj=left.decode().split(' ',2)
        return {'mode':mode,'type':typ,'object':obj}
    except Exception:return None


def blob_bytes(repo:Path,entry):
    if not entry or entry['type']!='blob':return None
    return run_git(repo,'cat-file','blob',entry['object'])


def blob_size(repo:Path,entry):
    if not entry or entry['type']!='blob':return 0
    raw=run_git(repo,'cat-file','-s',entry['object'])
    return int(raw.decode().strip())


def git_change_snapshot(repo:Path,base:str,head:str):
    """Metadata-only canonical Git snapshot used to cross-check evidence."""
    rows=[]
    for status,old,path in changed_entries(repo,base,head):
        code=status[0] if status else '?';ctype={'A':'ADDED','D':'DELETED','M':'MODIFIED','R':'RENAMED','C':'COPIED','T':'TYPE_CHANGED','U':'UNMERGED'}.get(code,'UNKNOWN')
        be=tree_entry(repo,base,old or path) if ctype!='ADDED' else None
        he=tree_entry(repo,head,path) if ctype!='DELETED' else None
        rows.append({'path':path,'old_path':old,'change_type':ctype,
          'base_blob_sha':be['object'] if be and be['type']=='blob' else None,
          'head_blob_sha':he['object'] if he and he['type']=='blob' else None,
          'mode_before':be['mode'] if be else None,'mode_after':he['mode'] if he else None,
          'base_type':be['type'] if be else None,'head_type':he['type'] if he else None})
    return rows


def load_checker(root:Path):
    spec=importlib.util.spec_from_file_location('tdc_checker',root/'checker.py')
    mod=importlib.util.module_from_spec(spec);assert spec and spec.loader;spec.loader.exec_module(mod)
    return mod


def encoding_conf(encs, sensor_cfg=None):
    vals={x for x in encs if x}
    if not vals:return 'UNKNOWN',False
    ecfg=(sensor_cfg or {}).get('encoding',{})
    high=set(ecfg.get('high',ENC_HIGH));medium=set(ecfg.get('medium',ENC_MED))
    fallback=any(x=='latin-1-fallback' for x in vals)
    if vals <= high:return 'HIGH',fallback
    if medium and vals <= (high|medium):return 'MEDIUM',fallback
    return 'LOW',fallback


def language(path:str):return LANG.get(Path(path).suffix.lower())

def path_flags(path:str):
    parts={x.lower() for x in PurePosixPath(path).parts}
    low=path.lower()
    generated=bool(parts & GENERATED_PARTS) or low.endswith(('.min.js','.min.css','.generated.py','.g.cs','.designer.cs'))
    vendor=bool(parts & VENDOR_PARTS)
    return generated,vendor


def is_test_path(path:str)->bool:
    p=normalize_repo_path(path).lower();parts=p.split('/');name=parts[-1]
    if any(x in {'test','tests','__tests__','spec','specs'} for x in parts[:-1]):return True
    if name.startswith('test_') or name.endswith('_test.py') or name.endswith('_test.go'):return True
    if re.search(r'\.(?:test|spec)\.[^.]+$',name):return True
    return False


def weakening_signals(repo:Path,base:str,head:str,path:str,change_type:str,old_path:str|None=None,scan_diff:bool=True):
    out=[];test_path=is_test_path(path) or bool(old_path and is_test_path(old_path))
    if change_type=='DELETED' and test_path:
        out.append({'kind':'test_deleted','path':path,'evidence':'test file deleted'})
    args=['diff','--find-renames','--unified=0','--no-ext-diff',base,head,'--']
    if old_path:args.append(old_path)
    args.append(path)
    raw=run_git(repo,*args,check=False).decode('utf-8','replace') if scan_diff else ''
    added=[x[1:] for x in raw.split('\n') if x.startswith('+') and not x.startswith('+++')]
    deleted=[x[1:] for x in raw.split('\n') if x.startswith('-') and not x.startswith('---')]
    global_patterns=[
      ('lint_suppression_added',re.compile(r'(?i)(eslint-disable|@ts-ignore|@ts-nocheck|noinspection|\bnolint\b)')),
      ('coverage_exclusion_added',re.compile(r'(?i)(pragma:\s*no\s*cover|istanbul\s+ignore|coverage:\s*ignore)')),
    ]
    for kind,rx in global_patterns:
        if any(rx.search(x) for x in added):out.append({'kind':kind,'path':path,'evidence':kind.replace('_',' ')})
    if test_path:
        skip_rx=re.compile(r'(?i)(pytest\.mark\.(?:skip|xfail)|\bskip\s*\(|\btest\.skip\s*\(|\bxit\s*\(|@Disabled\b|\bt\.Skip\s*\()')
        if any(skip_rx.search(x) for x in added):out.append({'kind':'test_skip_added','path':path,'evidence':'test skip/xfail added'})
        if any(re.search(r'\bassert\b|\bexpect\s*\(',x) for x in deleted):out.append({'kind':'assertion_removed','path':path,'evidence':'test assert/expect line removed'})
    seen=set();res=[]
    for row in out:
        k=(row['kind'],row['path'])
        if k not in seen:seen.add(k);res.append(row)
    return res


def reconstruct(a,b,ops):
    out=[]
    for tag,i1,i2,j1,j2 in ops:
        if tag=='equal':out.extend(a[i1:i2])
        elif tag in {'insert','replace'}:out.extend(b[j1:j2])
        elif tag=='delete':pass
        else:raise ValueError(tag)
    return out


def dep_version(name):
    try:return importlib.metadata.version(name)
    except Exception:return None


def main():
    ap=argparse.ArgumentParser(description='Git-aware TextDiff evidence adapter v2.4')
    ap.add_argument('--repo',required=True);ap.add_argument('--repository',required=True)
    ap.add_argument('--base',required=True,help='Trusted base ref/tip; adapter compares merge-base(base, head) to head')
    ap.add_argument('--head',required=True);ap.add_argument('--work-unit')
    ap.add_argument('--textdiff-root',default=str(ROOT/'vendor/TextDiffChecker_v1.4.6-harness.1'))
    ap.add_argument('--output',required=True);ap.add_argument('--policy',default=str(ROOT/'policy/protected-paths.yml'))
    ns=ap.parse_args();t0=time.perf_counter();repo=Path(ns.repo).resolve();tdroot=Path(ns.textdiff_root).resolve()
    checker=load_checker(tdroot);base_tip=resolve_commit(repo,ns.base);head=resolve_commit(repo,ns.head);base=merge_base(repo,base_tip,head)
    entries=changed_entries(repo,base,head);cfg=load_yaml(ns.policy);sensor_cfg=load_yaml(ROOT/'policy/sensor-policy.yml');raw_cfg=sensor_cfg.get('raw_data',{})
    if any(bool(raw_cfg.get(k)) for k in ('persist_source_bodies','persist_hunks','persist_trace_events')):
        raise SystemExit('raw_data persistence must remain disabled for the evidence adapter')
    all_paths=[]
    for _,old,new in entries:
        if old:all_paths.append(old)
        all_paths.append(new)
    hits=classify_paths(all_paths,cfg);protected=sorted(set(sum(hits.values(),[])))
    files=[];all_weak=[];apply_ok=True;had_error=False;coverage_gap=False;nontext_sensitive=False
    for status,old,path in entries:
        code=status[0] if status else '?';ctype={'A':'ADDED','D':'DELETED','M':'MODIFIED','R':'RENAMED','C':'COPIED','T':'TYPE_CHANGED','U':'UNMERGED'}.get(code,'UNKNOWN')
        be=tree_entry(repo,base,old or path) if ctype!='ADDED' else None;he=tree_entry(repo,head,path) if ctype!='DELETED' else None
        symlink=bool((be and be['mode']=='120000') or (he and he['mode']=='120000'));submodule=bool((be and be['type']=='commit') or (he and he['type']=='commit'))
        max_blob=max(blob_size(repo,be),blob_size(repo,he));too_large=max_blob > getattr(checker,'SIZE_LIMIT',10*1024*1024)
        gen,vendor=path_flags(path);weak=weakening_signals(repo,base,head,path,ctype,old,scan_diff=not too_large);all_weak.extend(weak)
        row={'path':path,'old_path':old,'change_type':ctype,'base_blob_sha':be['object'] if be and be['type']=='blob' else None,'head_blob_sha':he['object'] if he and he['type']=='blob' else None,
             'mode_before':be['mode'] if be else None,'mode_after':he['mode'] if he else None,'symlink':symlink,'submodule':submodule,'binary':False,'generated':gen,'vendor':vendor,'language':language(path),
             'encoding':{'base':None,'head':None,'confidence':'UNKNOWN','lossless_fallback_used':False},'status':'SKIPPED','skip_reason':None,'lines':{'a':0,'b':0},
             'diff':{'hunk_count':0,'changed_lines':0,'approx':False,'quality_class':'NOT_APPLICABLE','algorithm_path':[],'trace_digest':'0'*64},'weakening_signals':weak}
        blob_binding_invalid = (
            (ctype=='MODIFIED' and (not be or be.get('type')!='blob' or not he or he.get('type')!='blob')) or
            (ctype=='RENAMED' and (not be or be.get('type')!='blob' or not he or he.get('type')!='blob')) or
            (ctype=='COPIED' and (not be or be.get('type')!='blob' or not he or he.get('type')!='blob'))
        )
        if blob_binding_invalid and not (submodule or symlink):
            row['status']='ERROR';row['skip_reason']='missing_git_blob_binding';files.append(row);had_error=True;coverage_gap=True;continue
        if submodule or symlink:
            row['skip_reason']='submodule' if submodule else 'symlink';files.append(row);coverage_gap=True;nontext_sensitive=True;continue
        if too_large:
            row['skip_reason']='size_limit';files.append(row);had_error=True;coverage_gap=True;continue
        try:
            bb=blob_bytes(repo,be) if be else None;hb=blob_bytes(repo,he) if he else None
            if be is None:at,am='',None
            else:
                try:at,am=checker.decode_text_bytes(bb or b'')
                except checker.BinaryFileError:at=None;am=None
            if he is None:bt,bm='',None
            else:
                try:bt,bm=checker.decode_text_bytes(hb or b'')
                except checker.BinaryFileError:bt=None;bm=None
            if (be and at is None) or (he and bt is None):
                row['binary']=True;row['status']='BINARY';row['skip_reason']='binary';files.append(row);coverage_gap=True;nontext_sensitive=True;continue
            at=at or '';bt=bt or '';a=checker._split_text_lines(at);b=checker._split_text_lines(bt);conf,lf=encoding_conf([(am or {}).get('encoding'),(bm or {}).get('encoding')],sensor_cfg)
            row['encoding']={'base':(am or {}).get('encoding'),'head':(bm or {}).get('encoding'),'confidence':conf,'lossless_fallback_used':lf};row['lines']={'a':len(a),'b':len(b)}
            _,stats,ops,tr=checker.diff_texts_with_trace(a,b,old or path,path)
            # SequenceMatcher is a useful heuristic, but ordinary small edits can be
            # cheaply proven optimal with bounded Myers.  Upgrade only after an
            # independent exact reconstruction succeeds.
            if stats['quality_class']=='HEURISTIC' and max(len(a),len(b))<=512:
                try:
                    a_id,b_id=checker._line_ids(a,b,False)
                    exact_ops=checker._myers_opcodes(a_id,b_id,None,d_cap=512)
                    if reconstruct(a,b,exact_ops)==b:
                        ops=exact_ops
                        non_equal=[x for x in ops if x[0]!='equal']
                        stats['hunks']=len(non_equal)
                        stats['changed_lines']=sum(max(x[2]-x[1],x[4]-x[3]) for x in non_equal)
                        stats['quality_class']='PROVEN_EXACT';stats['approx']=False
                        tr={'api_version':tr.get('api_version'),'quality_class':'PROVEN_EXACT',
                            'algorithm_path':list(tr.get('algorithm_path',[]))+['adapter_full_myers_verify'],
                            'events':list(tr.get('events',[]))+[{'event':'adapter_full_myers_verify','quality':'PROVEN_EXACT','a_len':len(a),'b_len':len(b),'d_cap':512}]}
                except Exception:
                    pass
            ok=(reconstruct(a,b,ops)==b);apply_ok &= ok
            row['diff']={'hunk_count':stats['hunks'],'changed_lines':stats['changed_lines'],'approx':stats['approx'],'quality_class':stats['quality_class'],'algorithm_path':tr['algorithm_path'],'trace_digest':object_digest(tr)}
            row['status']='ANALYZED';row['skip_reason']=None
        except Exception as exc:
            had_error=True;coverage_gap=True;apply_ok=False;row['status']='ERROR';row['skip_reason']=type(exc).__name__
        files.append(row)
    analyzed=[f for f in files if f['status']=='ANALYZED'];qualities=[f['diff']['quality_class'] for f in analyzed];q='NOT_APPLICABLE' if not qualities else max(qualities,key=lambda x:QUALITY_ORDER[x])
    expected=sensor_cfg.get('trusted_tool',{})
    original_package=ROOT/'vendor/TextDiffChecker_v1_4_6_original.zip'
    # The distributable package may retain the original binary archive, while the
    # public source tree intentionally omits it.  Runtime trust is bound to the
    # executable checker and dependency declarations; the original archive digest is
    # retained as provenance metadata when the archive is absent.
    package_hash=sha256_file(original_package) if original_package.is_file() else expected.get('original_package_sha256')
    actual_hashes={'checker_sha256':sha256_file(tdroot/'checker.py'),'original_package_sha256':package_hash,'vendor_requirements_sha256':sha256_file(tdroot/'requirements.txt'),'harness_requirements_sha256':sha256_file(ROOT/'requirements.txt')}
    required_runtime_pins={'checker_sha256','vendor_requirements_sha256','harness_requirements_sha256'}
    hash_mismatch=[k for k,v in actual_hashes.items() if (k in required_runtime_pins and (not expected.get(k) or expected.get(k)!=v)) or (k=='original_package_sha256' and original_package.is_file() and expected.get(k)!=v)]
    missing_pins=sorted(k for k in required_runtime_pins if not expected.get(k))
    regex_ok=bool(getattr(checker,'_HAS_REGEX',False));tdcfg=sensor_cfg.get('textdiff',{});regex_required=bool(tdcfg.get('trusted_runtime_requires_regex_timeout',True));quality_allowed=q in set(tdcfg.get('accepted_quality_classes',[]))
    runtime_ok=(regex_ok or not regex_required) and quality_allowed and not had_error and not coverage_gap and apply_ok and not hash_mismatch
    invariants=[
      {'id':'git-merge-base-head-binding','status':'passed','evidence':f'{base[:12]}...{head[:12]} (base tip {base_tip[:12]})'},
      {'id':'apply-opcodes-reconstruct-target','status':'passed' if apply_ok else 'failed','evidence':'all analyzed file transforms reconstruct target' if apply_ok else 'at least one file failed reconstruction'},
      {'id':'regex-timeout-runtime','status':'passed' if regex_ok else 'failed','evidence':'regex timeout engine available' if regex_ok else 'stdlib re fallback detected'},
      {'id':'trusted-tool-hash','status':'passed' if not hash_mismatch else 'failed','evidence':'pinned tool/dependency hashes match' if not hash_mismatch else 'mismatch: '+','.join(hash_mismatch)},
      {'id':'nontext-coverage','status':'failed' if nontext_sensitive else 'passed','evidence':'symlink/submodule/binary requires higher review' if nontext_sensitive else 'no sensitive non-text change'},
      {'id':'repeat-determinism','status':'unknown','evidence':'not rerun by default adapter'}]
    reasons=[]
    if regex_required and not regex_ok:reasons.append('regex_timeout_unavailable')
    if not quality_allowed:reasons.append('quality_class_not_accepted')
    if had_error or coverage_gap:reasons.append('file_analysis_or_coverage_gap')
    if nontext_sensitive:reasons.append('nontext_sensitive_change')
    if not apply_ok:reasons.append('opcode_reconstruction_failed')
    if hash_mismatch:reasons.append('trusted_tool_hash_mismatch')
    if missing_pins:reasons.append('trusted_tool_pin_missing')
    tool={'name':'TextDiffChecker','product_version':'1.4.6','harness_api_version':getattr(checker,'HARNESS_API_VERSION','unknown'),
      'package_sha256':actual_hashes['original_package_sha256'],'package_present':original_package.is_file(),'checker_sha256':actual_hashes['checker_sha256'],'syntax_db_sha256':sha256_file(tdroot/'syntax_db.json'),
      'dependencies_sha256':actual_hashes['vendor_requirements_sha256'],'harness_dependencies_sha256':actual_hashes['harness_requirements_sha256'],
      'runtime_dependencies':{'python':sys.version.split()[0],'jsonschema':dep_version('jsonschema'),'PyYAML':dep_version('PyYAML'),'regex':dep_version('regex')},
      'config_sha256':sha256_file(ROOT/'policy/sensor-policy.yml'),'regex_timeout_available':regex_ok}
    ev={'schema_version':'2.4','tool':tool,'binding':{'repository':ns.repository,'work_unit':ns.work_unit,'base_ref_sha':base_tip,'base_sha':base,'head_sha':head,'comparison_mode':'merge-base'},
        'summary':{'files_changed':len(files),'a_lines':sum(f['lines']['a'] for f in files),'b_lines':sum(f['lines']['b'] for f in files),'hunk_count':sum(f['diff']['hunk_count'] for f in files),'changed_lines':sum(f['diff']['changed_lines'] for f in files),'quality_class':q,'protected_candidates':protected,'weakening_signals':all_weak,'nontext_sensitive_paths':sorted({f['path'] for f in files if f['symlink'] or f['submodule'] or f['binary']})},
        'files':files,'performance':{'elapsed_ms':round((time.perf_counter()-t0)*1000,3),'peak_memory_mb':None,'timed_out':False,'cancelled':False},'invariants':invariants,
        'trust':{'runtime_safety':'PASS' if runtime_ok else 'FAIL','trusted_for_gate':runtime_ok,'reasons':sorted(set(reasons))},'semantic_digest':'','output_digest':''}
    semantic_view={k:v for k,v in ev.items() if k not in {'performance','semantic_digest','output_digest'}};ev['semantic_digest']=object_digest(semantic_view);ev['output_digest']=object_digest(ev,'output_digest');write_json(ns.output,ev);print(ns.output)

if __name__=='__main__':main()
