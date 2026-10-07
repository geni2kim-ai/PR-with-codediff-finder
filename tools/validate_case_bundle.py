from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_case_record import semantic_errors as case_errors
from case_ledger import load_events,validate_events,validate_anchor,canonical_anchor_path,default_anchor_path
SCHEMA=json.loads((ROOT/'schemas/case-record.schema.json').read_text())

def errors(case,ledger=None,anchor=None,require_hmac=False,hmac_key=None):
    e=[x.message for x in Draft202012Validator(SCHEMA).iter_errors(case)]+case_errors(case)
    if not ledger:return e
    events=load_events(ledger);e+=validate_events(events,case.get('case_id'))
    anchor=anchor or default_anchor_path(ledger);e+=validate_anchor(ledger,anchor,events,case.get('case_id'),hmac_key,require_hmac)
    completed={(x.get('payload',{}).get('level'),x.get('payload',{}).get('result_digest')) for x in events if x.get('event_type')=='REVIEW_COMPLETED'}
    humans={(x.get('payload',{}).get('review_id'),x.get('payload',{}).get('result_digest')) for x in events if x.get('event_type')=='HUMAN_DECISION'}
    for r in case.get('review_trail',[]):
        if r['level']=='HUMAN':
            if (r['review_id'],r['result_digest']) not in humans:e.append(f'human review missing matching ledger event: {r["review_id"]}')
        elif (r['level'],r['result_digest']) not in completed:e.append(f'review trail missing matching ledger event: {r["review_id"]}')
    sensor=[x for x in events if x.get('event_type')=='SENSOR_ACCEPTED']
    if sensor and sensor[-1].get('payload',{}).get('evidence_digest')!=case.get('sensor',{}).get('evidence_digest'):e.append('case sensor digest does not match ledger')
    outcome=case.get('outcome',{});oe=[x for x in events if x.get('event_type')=='OUTCOME_RECORDED'];ie=[x for x in events if x.get('event_type')=='INCIDENT_RECORDED']
    nondefault=outcome.get('author_response')!='no_response' or outcome.get('merged') or outcome.get('post_merge_status')!='unknown'
    if nondefault and not oe:e.append('case outcome changed without OUTCOME_RECORDED ledger event')
    if oe:
        expected=dict(oe[-1].get('payload') or {})
        if ie and ie[-1].get('seq',0)>oe[-1].get('seq',0):
            ip=ie[-1].get('payload') or {};expected['post_merge_status']=ip.get('kind');expected['incident_ref']=ip.get('incident_ref')
        if expected!=outcome:e.append('case outcome does not match ledger-derived outcome state')
    if outcome.get('post_merge_status') in {'incident','regression'} and not ie:e.append('incident outcome missing INCIDENT_RECORDED event')
    return e

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--ledger');ap.add_argument('--anchor');ap.add_argument('--require-hmac',action='store_true');ap.add_argument('--hmac-key-env',default='MAESTRO_LEDGER_HMAC_KEY');ns=ap.parse_args();case=json.loads(Path(ns.case).read_text());errs=errors(case,ns.ledger,ns.anchor,ns.require_hmac,os.environ.get(ns.hmac_key_env))
    if errs:print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
    print('VALID')
if __name__=='__main__':main()
