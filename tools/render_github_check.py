from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_review_cycle import semantic_errors
from validate_case_bundle import errors as bundle_errors
from case_ledger import default_anchor_path,load_events,validate_events,validate_anchor
from human_decision_attestation import validate as validate_human_attestation,digest as human_attestation_digest
from jsonschema import Draft202012Validator
SCHEMA=json.loads((ROOT/'schemas/review-cycle.schema.json').read_text())

def _human_proof_errors(c,events,cycle_path,human_attestation,human_key,case_path,ledger,anchor,ledger_key):
    e=[];state=c.get('state')
    if state not in {'HUMAN_CONFIRMED','HUMAN_REJECTED'}:return e
    verdict='CONFIRMED' if state=='HUMAN_CONFIRMED' else 'REJECTED'
    closes=[x for x in events if x.get('event_type')=='CYCLE_CLOSED']
    close=(closes[-1].get('payload') or {}) if closes else {}
    rid=close.get('human_review_id');ad=close.get('human_attestation_digest')
    if not rid:e.append('human terminal close missing human_review_id')
    if not ad:e.append('human terminal close missing human_attestation_digest')
    decisions=[x for x in events if x.get('event_type')=='HUMAN_DECISION' and (x.get('payload') or {}).get('review_id')==rid]
    if not decisions:e.append('matching HUMAN_DECISION ledger event missing');return e
    hp=decisions[-1].get('payload') or {}
    if hp.get('verdict')!=verdict:e.append('HUMAN_DECISION verdict does not match terminal state')
    if hp.get('head_sha')!=c.get('binding',{}).get('head_sha'):e.append('HUMAN_DECISION head_sha mismatch')
    if hp.get('attestation_digest')!=ad:e.append('human attestation digest mismatch between decision and close')

    att_path=Path(human_attestation) if human_attestation else Path(cycle_path).parent/'human-decision-attestation.json'
    if not att_path.is_file():e.append('persisted human decision attestation missing');return e
    try:att=json.loads(att_path.read_text())
    except Exception:e.append('persisted human decision attestation invalid JSON');return e
    if human_attestation_digest(att)!=ad:e.append('persisted human attestation digest mismatch')
    actor=hp.get('actor_id')
    if not actor:e.append('HUMAN_DECISION actor_id missing')
    ae=validate_human_attestation(att,case_id=c.get('case_id'),actor_id=actor,verdict=verdict,head_sha=c.get('binding',{}).get('head_sha'),key=human_key)
    e.extend(ae)

    cp=Path(case_path) if case_path else Path(cycle_path).parent/'case-record.json'
    if not cp.is_file():e.append('case record required for human terminal render')
    else:
        try:
            case=json.loads(cp.read_text())
            e.extend(bundle_errors(case,ledger,anchor,c.get('execution_mode')=='ENFORCED',ledger_key))
            matching=[r for r in case.get('review_trail',[]) if r.get('review_id')==rid and r.get('level')=='HUMAN']
            if not matching:e.append('case record missing matching HUMAN review')
            elif matching[-1].get('result_digest')!=hp.get('result_digest'):e.append('case HUMAN result digest mismatch')
        except Exception as exc:e.append('case record human proof unreadable: '+type(exc).__name__)
    return e

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('cycle');ap.add_argument('--output',required=True);ap.add_argument('--name',default='Maestro Review Gate')
    ap.add_argument('--ledger');ap.add_argument('--anchor');ap.add_argument('--case');ap.add_argument('--human-attestation')
    ap.add_argument('--hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');ap.add_argument('--human-key-env',default='MAESTRO_HUMAN_DECISION_KEY')
    ns=ap.parse_args();cycle_path=Path(ns.cycle);c=json.loads(cycle_path.read_text())
    errs=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(c)]+semantic_errors(c)
    if errs:raise SystemExit('invalid cycle: '+'; '.join(errs))
    ledger=Path(ns.ledger) if ns.ledger else cycle_path.parent/'case-events.jsonl';anchor=Path(ns.anchor) if ns.anchor else default_anchor_path(ledger)
    ledger_key=os.environ.get(ns.hmac_key_env);events=load_events(ledger)
    errs=validate_events(events,c.get('case_id'))+validate_anchor(ledger,anchor,events,c.get('case_id'),ledger_key,require_hmac=(c.get('execution_mode')=='ENFORCED'))
    closes=[x for x in events if x.get('event_type')=='CYCLE_CLOSED']
    if not closes:errs.append('CYCLE_CLOSED ledger event missing')
    else:
        p=closes[-1].get('payload',{})
        if p.get('cycle_digest')!=c.get('cycle_digest'):errs.append('cycle digest does not match latest CYCLE_CLOSED ledger event')
        if p.get('state')!=c.get('state'):errs.append('cycle state does not match latest CYCLE_CLOSED ledger event')
        if p.get('gate_conclusion')!=c.get('gate_conclusion'):errs.append('cycle gate does not match latest CYCLE_CLOSED ledger event')
    if c.get('state') in {'HUMAN_CONFIRMED','HUMAN_REJECTED'}:
        human_key=os.environ.get(ns.human_key_env)
        if not human_key:errs.append('human decision key unavailable for terminal human render')
        else:errs+=_human_proof_errors(c,events,cycle_path,ns.human_attestation,human_key,ns.case,ledger,anchor,ledger_key)
    if errs:raise SystemExit('untrusted cycle/ledger: '+'; '.join(errs))

    reasons=', '.join(c['escalation_reasons'][:8]) if c['escalation_reasons'] else 'none'
    summary=f"state={c['state']} | required={c['required_level']} | achieved={c['achieved_level']} | reasons={reasons}"
    shadow=c.get('execution_mode')=='SHADOW';conclusion='neutral' if shadow else c['gate_conclusion'];name=('[SHADOW] '+ns.name) if shadow else ns.name
    if shadow:summary += f" | predicted_conclusion={c['gate_conclusion']} | non-blocking preview"
    payload={'name':name,'head_sha':c['binding']['head_sha'],'status':'completed','conclusion':conclusion,'output':{'title':f"Review {conclusion}: {c['state']}",'summary':summary}}
    Path(ns.output).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(ns.output)

if __name__=='__main__':main()
