from __future__ import annotations
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from validate_review_cycle import semantic_errors
from jsonschema import Draft202012Validator
SCHEMA=json.loads((ROOT/'schemas/review-cycle.schema.json').read_text())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('cycle');ap.add_argument('--output',required=True);ap.add_argument('--name',default='Maestro Review Gate');ns=ap.parse_args();c=json.loads(Path(ns.cycle).read_text())
    errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(c)]+semantic_errors(c)
    if errs:raise SystemExit('invalid cycle: '+'; '.join(errs))
    reasons=', '.join(c['escalation_reasons'][:8]) if c['escalation_reasons'] else 'none'
    summary=f"state={c['state']} | required={c['required_level']} | achieved={c['achieved_level']} | reasons={reasons}"
    shadow=c.get('execution_mode')=='SHADOW'
    conclusion='neutral' if shadow else c['gate_conclusion']
    name=('[SHADOW] '+ns.name) if shadow else ns.name
    if shadow: summary += f" | predicted_conclusion={c['gate_conclusion']} | non-blocking preview"
    payload={'name':name,'head_sha':c['binding']['head_sha'],'status':'completed','conclusion':conclusion,'output':{'title':f"Review {conclusion}: {c['state']}",'summary':summary}}
    Path(ns.output).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(ns.output)
if __name__=='__main__':main()
