from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
from common import object_digest
from sanitize_review_text import scan_stage_result
TASK_SCHEMA=json.loads((ROOT/'schemas/reviewer-task.schema.json').read_text())
SCHEMA=json.loads((ROOT/'schemas/reviewer-stage-result.schema.json').read_text())
def semantic_errors(o,task=None):
    e=[]
    if o.get('result_digest')!=object_digest(o,'result_digest'):e.append('result_digest mismatch')
    findings=o.get('findings',[])
    if o.get('verdict')=='PASS' and findings:e.append('PASS must have zero findings')
    if o.get('verdict')=='FINDINGS' and not findings:e.append('FINDINGS requires findings')
    nits=sum(f.get('severity')=='nit' for f in findings)
    if task:
        if o.get('task_id')!=task.get('task_id') or o.get('case_id')!=task.get('case_id') or o.get('level')!=task.get('level'):e.append('task/result identity mismatch')
        if o.get('binding',{}).get('repository')!=task.get('binding',{}).get('repository') or o.get('binding',{}).get('reviewed_head_sha')!=task.get('binding',{}).get('head_sha'):e.append('task/result binding mismatch')
        if o.get('evidence_digest')!=task.get('sensor',{}).get('evidence_digest'):e.append('task/result evidence digest mismatch')
        c=task.get('reviewer_contract',{});r=o.get('reviewer',{})
        for k in ('node_id','model','prompt_digest','skill_digest','policy_digest','standards_digest','worker_command_digest'):
            if r.get(k)!=c.get(k):e.append(f'reviewer provenance mismatch: {k}')
        if task['level'] in {'L2','ADVERSARIAL'} and not r.get('independent_context'):e.append(f'{task["level"]} must report independent_context=true')
        if len(findings)>task['limits']['max_findings']:e.append('finding count exceeds task limit')
        if nits>task['limits']['max_nits']:e.append('nit count exceeds task limit')
    reported=o.get('output_safety',{})
    computed=scan_stage_result(o)
    if reported != computed:e.append('output_safety does not match harness-computed safety scan')
    if computed['external_urls_present']:e.append('external URL/domain present in reviewer-controlled text')
    if computed['markdown_images_present']:e.append('image markup present in reviewer-controlled text')
    if computed['mentions_present']:e.append('mention-like token present in reviewer-controlled text')
    if not computed['secret_scan_passed']:e.append('secret-like material present in reviewer-controlled text')
    return e

def validate(o,task=None):
    return [x.message for x in Draft202012Validator(SCHEMA).iter_errors(o)] + semantic_errors(o,task)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('result');ap.add_argument('--task');ns=ap.parse_args();o=json.loads(Path(ns.result).read_text());task=json.loads(Path(ns.task).read_text()) if ns.task else None;errs=validate(o,task)
    if errs:
        print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
    print('VALID')
if __name__=='__main__':main()
