from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
LEVEL={'L1':1,'L2':2,'ADVERSARIAL':3,'HUMAN':4}

def semantic_errors(o):
    e=[];trail=o.get('review_trail',[]);ids=set();seen=set();head=o.get('binding',{}).get('head_sha');ev=o.get('sensor',{}).get('evidence_digest')
    for i,r in enumerate(trail):
        rid=r['review_id']
        if rid in ids:e.append(f'duplicate review_id: {rid}')
        ids.add(rid)
        p=r.get('parent_review_id')
        if p is not None and p not in seen:e.append(f'{rid}: parent_review_id must reference an earlier review')
        seen.add(rid)
        if r['reviewed_head_sha']!=head:e.append(f'{rid}: reviewed_head_sha does not match case head')
        if r['evidence_digest']!=ev:e.append(f'{rid}: evidence_digest does not match case sensor')
        if LEVEL[r['achieved_level']] < LEVEL[r['level']]:e.append(f'{rid}: achieved_level lower than reviewer level')
        if LEVEL[r['requested_level']] < LEVEL[r['level']]:e.append(f'{rid}: requested_level lower than reviewer level')
        if r['level'] in {'L2','ADVERSARIAL'} and not r['independent_context']:e.append(f'{rid}: {r["level"]} must use independent_context')
        if r['level']=='HUMAN' and r.get('model') is not None:e.append(f'{rid}: HUMAN model must be null')
        if r['level']!='HUMAN' and r.get('model') is None:e.append(f'{rid}: model provenance required')
        if 'material_finding_signatures' in r:
            sigs=r.get('material_finding_signatures') or [];count=int(r.get('material_finding_count',0))
            if len(sigs)!=count:e.append(f'{rid}: material_finding_signatures count mismatch')
            sig_keys=[str(x).split('|',1)[1] for x in sigs if isinstance(x,str) and '|' in x]
            keys=r.get('material_finding_keys')
            if isinstance(keys,list) and set(sig_keys)!=set(str(x) for x in keys):e.append(f'{rid}: material_finding_signatures/key mismatch')
            if sum(str(x).startswith('major|') for x in sigs)!=int(r.get('major_finding_count',0)):e.append(f'{rid}: material_finding_signatures major count mismatch')
            if sum(str(x).startswith('blocker|') for x in sigs)!=int(r.get('blocker_finding_count',0)):e.append(f'{rid}: material_finding_signatures blocker count mismatch')
    # A case claiming a resolved adversarial review must actually contain one.
    if 'adversarial_reviewed' in set(o.get('labels',[])) and not any(r['level']=='ADVERSARIAL' for r in trail):e.append('adversarial_reviewed label without ADVERSARIAL trail entry')
    return e

def main():
    ap=argparse.ArgumentParser();ap.add_argument('json');ns=ap.parse_args();o=json.loads(Path(ns.json).read_text());schema=json.loads((ROOT/'schemas/case-record.schema.json').read_text())
    se=list(Draft202012Validator(schema).iter_errors(o));ee=semantic_errors(o)
    if se or ee:
        for x in se:print('SCHEMA:',x.message)
        for x in ee:print('SEMANTIC:',x)
        raise SystemExit(1)
    print('PASS')
if __name__=='__main__':main()
