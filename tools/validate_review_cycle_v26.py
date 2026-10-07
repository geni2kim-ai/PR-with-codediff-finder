from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from common import object_digest
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/review-cycle-v26.schema.json').read_text())
LEVEL={'SENSOR':0,'L1':1,'L2':2,'ADVERSARIAL':3,'HUMAN':4}

def semantic_errors(o):
    e=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(o)]
    if o.get('cycle_digest')!=object_digest(o,'cycle_digest'):e.append('cycle_digest mismatch')
    if LEVEL.get(o.get('achieved_level'),-1)<LEVEL.get(o.get('required_level'),99) and o.get('gate_conclusion') not in {'action_required','cancelled'}:e.append('unreached authority cannot have mergeable gate')
    if o.get('state')=='HUMAN_CONFIRMED' and (o.get('required_level')!='HUMAN' or o.get('achieved_level')!='HUMAN' or o.get('gate_conclusion')!='success'):e.append('invalid HUMAN_CONFIRMED transition')
    if o.get('state')=='HUMAN_REJECTED' and (o.get('required_level')!='HUMAN' or o.get('achieved_level')!='HUMAN' or o.get('gate_conclusion')!='failure'):e.append('invalid HUMAN_REJECTED transition')
    return e
