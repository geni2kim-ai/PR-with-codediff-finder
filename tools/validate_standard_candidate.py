from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator
from common import object_digest
ROOT=Path(__file__).resolve().parents[1];SCHEMA=json.loads((ROOT/'schemas/standard-candidate.schema.json').read_text())
def semantic_errors(o):
    e=[]
    if o.get('candidate_digest')!=object_digest(o,'candidate_digest'):e.append('candidate_digest mismatch')
    if o.get('approval',{}).get('approved') is not False:e.append('candidate cannot self-approve')
    return e
def main():
    ap=argparse.ArgumentParser();ap.add_argument('json');ns=ap.parse_args();o=json.loads(Path(ns.json).read_text());errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(o)]+semantic_errors(o)
    if errs:[print('INVALID',x) for x in errs];raise SystemExit(1)
    print('VALID')
if __name__=='__main__':main()
