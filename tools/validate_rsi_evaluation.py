from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from common import sha256_file
from policy_engine import load_yaml

def derive(o,cfg):
    w=cfg['weights'];overall=round(sum(float(o['scores'][k])*float(v) for k,v in w.items()),4)
    t=cfg['thresholds'];tags=set(o.get('failure_tags',[]));critical=bool(tags & set(cfg['critical_failure_tags']))
    rep=o.get('reproduction') or {};stable=rep.get('attempts',0)>=t['stable_attempts'] and rep.get('reproduced',0)>=t['stable_reproduced']
    occ=o.get('family_occurrences',0)
    p={'case_bank':critical or overall<t['case_bank_below'],
       'adversarial_required':critical or overall<t['adversarial_below'] or 'NOVEL-FAILURE-FAMILY' in tags,
       'improvement_candidate':critical or (overall<t['improvement_below'] and stable and occ>=t['family_occurrences'])}
    return overall,p

def semantic_errors(o,policy):
    cfg=load_yaml(policy);overall,p=derive(o,cfg);e=[]
    if abs(float(o['overall_score'])-overall)>1e-9:e.append(f'overall_score mismatch: stored={o["overall_score"]} computed={overall}')
    for k,v in p.items():
        if o['promotion'].get(k)!=v:e.append(f'promotion.{k} mismatch: stored={o["promotion"].get(k)} computed={v}')
    pd=sha256_file(policy)
    if o.get('derived_by',{}).get('policy_digest')!=pd:e.append('derived_by.policy_digest mismatch')
    rep=o.get('reproduction') or {}
    if rep.get('reproduced',0)>rep.get('attempts',0):e.append('reproduced cannot exceed attempts')
    return e

def main():
    ap=argparse.ArgumentParser();ap.add_argument('json');ap.add_argument('--policy',default=str(ROOT/'policy/rsi-scoring.yml'));ns=ap.parse_args()
    o=json.loads(Path(ns.json).read_text());schema=json.loads((ROOT/'schemas/rsi-evaluation.schema.json').read_text())
    se=list(Draft202012Validator(schema).iter_errors(o));ee=semantic_errors(o,ns.policy)
    if se or ee:
        for x in se:print('SCHEMA:',x.message)
        for x in ee:print('SEMANTIC:',x)
        raise SystemExit(1)
    print('PASS')
if __name__=='__main__':main()
