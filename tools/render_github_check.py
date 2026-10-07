from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_review_cycle import semantic_errors
from case_ledger import canonical_anchor_path,load_events,validate_events,validate_anchor
from jsonschema import Draft202012Validator
SCHEMA=json.loads((ROOT/'schemas/review-cycle.schema.json').read_text())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('cycle');ap.add_argument('--output',required=True);ap.add_argument('--name',default='Maestro Review Gate');ap.add_argument('--ledger');ap.add_argument('--anchor');ap.add_argument('--hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');ns=ap.parse_args();cycle_path=Path(ns.cycle);c=json.loads(cycle_path.read_text());errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(c)]+semantic_errors(c)
    if errs:raise SystemExit('invalid cycle: '+'; '.join(errs))
    ledger=Path(ns.ledger) if ns.ledger else cycle_path.parent/'case-events.jsonl';anchor=Path(ns.anchor) if ns.anchor else canonical_anchor_path(ledger);key=os.environ.get(ns.hmac_key_env);events=load_events(ledger);errs=validate_events(events,c.get('case_id'))+validate_anchor(ledger,anchor,events,c.get('case_id'),key,require_hmac=(c.get('execution_mode')=='ENFORCED'));closes=[x for x in events if x.get('event_type')=='CYCLE_CLOSED']
    if not closes:errs.append('CYCLE_CLOSED ledger event missing')
    else:
        p=closes[-1].get('payload',{})
        if p.get('cycle_digest')!=c.get('cycle_digest'):errs.append('cycle digest does not match latest CYCLE_CLOSED ledger event')
        if p.get('state')!=c.get('state'):errs.append('cycle state does not match latest CYCLE_CLOSED ledger event')
        if p.get('gate_conclusion')!=c.get('gate_conclusion'):errs.append('cycle gate does not match latest CYCLE_CLOSED ledger event')
    if errs:raise SystemExit('untrusted cycle/ledger: '+'; '.join(errs))
    reasons=', '.join(c['escalation_reasons'][:8]) if c['escalation_reasons'] else 'none';summary=f"state={c['state']} | required={c['required_level']} | achieved={c['achieved_level']} | reasons={reasons}";shadow=c.get('execution_mode')=='SHADOW';conclusion='neutral' if shadow else c['gate_conclusion'];name=('[SHADOW] '+ns.name) if shadow else ns.name
    if shadow:summary += f" | predicted_conclusion={c['gate_conclusion']} | non-blocking preview"
    payload={'name':name,'head_sha':c['binding']['head_sha'],'status':'completed','conclusion':conclusion,'output':{'title':f"Review {conclusion}: {c['state']}",'summary':summary}};Path(ns.output).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(ns.output)
if __name__=='__main__':main()
