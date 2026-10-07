from __future__ import annotations
import json,os,signal,subprocess,tempfile,threading,time
from pathlib import Path

def _kill_tree(p):
    if os.name!='nt':
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    else:
        try:p.kill()
        except Exception:pass

def run_worker(cmd,task,cfg):
    import run_review_cycle as legacy
    from validate_reviewer_task import validate as validate_task
    from validate_stage_result import validate as validate_stage
    from sanitize_review_text import scan_stage_result
    errs=validate_task(task)
    if errs:raise legacy.ReviewerExecutionError('INVALID_TASK','invalid reviewer task: '+'; '.join(errs))
    rt=cfg['runtime'];limit=int(rt['max_output_bytes']);stderr_limit=int(rt.get('max_stderr_bytes',min(limit,262144)));timeout=int(rt['timeout_seconds'])
    payload=json.dumps(task,ensure_ascii=False).encode('utf-8');start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='maestro-review-') as td:
        op=Path(td)/'stdout';ep=Path(td)/'stderr'
        with op.open('wb') as of,ep.open('wb') as ef:
            p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=of,stderr=ef,shell=False,env=legacy.safe_env(rt.get('environment_allowlist',[]),task),start_new_session=(os.name!='nt'))
            feed_error=[]
            def feed():
                try:
                    assert p.stdin is not None;p.stdin.write(payload);p.stdin.close()
                except Exception as exc:feed_error.append(type(exc).__name__)
            threading.Thread(target=feed,daemon=True).start()
            try:
                while p.poll() is None:
                    if time.monotonic()-start>timeout:_kill_tree(p);p.wait();raise legacy.ReviewerExecutionError('TIMEOUT',f'reviewer exceeded {timeout}s')
                    if (op.stat().st_size if op.exists() else 0)>limit:_kill_tree(p);p.wait();raise legacy.ReviewerExecutionError('OUTPUT_LIMIT',f'reviewer output exceeded {limit} bytes while running')
                    if (ep.stat().st_size if ep.exists() else 0)>stderr_limit:_kill_tree(p);p.wait();raise legacy.ReviewerExecutionError('STDERR_LIMIT',f'reviewer stderr exceeded {stderr_limit} bytes while running')
                    time.sleep(0.02)
            finally:
                if p.poll() is None:_kill_tree(p);p.wait()
                elif os.name!='nt':
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
        out=op.read_bytes();err_raw=ep.read_bytes();err=err_raw[:8192].decode('utf-8','replace')
        if p.returncode:raise legacy.ReviewerExecutionError('PROCESS_EXIT',f'reviewer exited {p.returncode}',err)
        if feed_error:raise legacy.ReviewerExecutionError('STDIN_WRITE','reviewer did not consume task input',err)
        if len(out)>limit:raise legacy.ReviewerExecutionError('OUTPUT_LIMIT',f'reviewer output exceeds {limit} bytes',err)
        try:r=json.loads(out.decode('utf-8'))
        except Exception as exc:raise legacy.ReviewerExecutionError('INVALID_JSON','reviewer did not emit one JSON object',err) from exc
    computed=scan_stage_result(r)
    if any((computed['external_urls_present'],computed['markdown_images_present'],computed['mentions_present'])) or not computed['secret_scan_passed']:
        raise legacy.ReviewerExecutionError('UNSAFE_OUTPUT','reviewer output failed harness-computed output safety scan')
    errs=validate_stage(r,task)
    if errs:raise legacy.ReviewerExecutionError('INVALID_RESULT','invalid reviewer result: '+'; '.join(errs))
    return r
