from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator
from common import object_digest
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/review-cycle.schema.json').read_text())
LEVEL={'SENSOR':0,'L1':1,'L2':2,'ADVERSARIAL':3,'HUMAN':4}

def semantic_errors(o):
    e=[]
    if o.get('cycle_digest')!=object_digest(o,'cycle_digest'):e.append('cycle_digest mismatch')
    if not o.get('current_head_verified') and o.get('state')!='STALE':e.append('unverified current head requires STALE')
    if LEVEL[o['achieved_level']]<LEVEL[o['required_level']] and o['gate_conclusion'] not in {'action_required','cancelled'}:e.append('unreached authority cannot have mergeable gate')
    levels=[x['level'] for x in o.get('stages',[])]
    if levels!=sorted(levels,key=lambda x:LEVEL[x]):e.append('stage order invalid')
    if len(levels)!=len(set(levels)):e.append('duplicate review level')
    if o['state']=='COMPLETE' and LEVEL[o['achieved_level']]<LEVEL[o['required_level']]:e.append('COMPLETE before required authority')
    if o.get('execution_mode')=='SHADOW' and o.get('gate_effective'):e.append('SHADOW cycle cannot have gate_effective=true')
    if o.get('execution_mode')=='ENFORCED' and not o.get('gate_effective'):e.append('ENFORCED cycle requires gate_effective=true')
    if o.get('state')=='COMPLETE' and not o.get('evidence_git_verified'):e.append('COMPLETE requires evidence_git_verified')
    if o.get('state')=='COMPLETE' and not o.get('worktree_clean_verified'):e.append('COMPLETE requires clean worktree')
    if o.get('execution_mode')=='ENFORCED' and not o.get('ledger_anchor_verified'):e.append('ENFORCED cycle requires verified ledger anchor')
    return e

def main():
    ap=argparse.ArgumentParser();ap.add_argument('json');ns=ap.parse_args();o=json.loads(Path(ns.json).read_text());errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(o)]+semantic_errors(o)
    if errs:[print('INVALID',x) for x in errs];raise SystemExit(1)
    print('VALID')
if __name__=='__main__':main()
