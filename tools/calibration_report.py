from __future__ import annotations
import argparse,json,sys,os
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_case_bundle import errors as bundle_errors
from policy_engine import load_yaml
LEVEL={'L1':1,'L2':2,'ADVERSARIAL':3,'HUMAN':4}
def safe_div(a,b):return round(a/b,4) if b else None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case-bank',required=True);ap.add_argument('--output',required=True);ap.add_argument('--limits',default=str(ROOT/'policy/limits.yml'));ns=ap.parse_args();root=Path(ns.case_bank);cases=[];invalid=[]
    for p in sorted(root.glob('*/case-record.json')):
        try:c=json.loads(p.read_text())
        except Exception as exc:invalid.append({'case_path':str(p),'reason':'invalid_json:'+type(exc).__name__});continue
        ledger=p.parent/'case-events.jsonl';anchor=p.parent/'case-events.anchor.json'
        try:anchor_obj=json.loads(anchor.read_text()) if anchor.exists() else {}
        except Exception:anchor_obj={}
        require_hmac=bool(anchor_obj.get('hmac_sha256'));errs=bundle_errors(c,ledger if ledger.exists() else None,anchor,require_hmac,os.environ.get('MAESTRO_LEDGER_HMAC_KEY'))
        if ledger.exists() and errs:invalid.append({'case_id':c.get('case_id'),'reason':'; '.join(errs[:8])});continue
        if not ledger.exists():invalid.append({'case_id':c.get('case_id'),'reason':'ledger_missing'});continue
        cases.append(c)
    per=defaultdict(lambda:{'reviews':0,'compared_to_final':0,'agree_final':0,'pass_then_incident':0});reversals=defaultdict(int);model=defaultdict(lambda:{'reviews':0,'compared_to_final':0,'agree_final':0});worker=defaultdict(lambda:{'reviews':0,'compared_to_final':0,'agree_final':0});sampling=defaultdict(lambda:{'cases':0,'l1_reviews':0,'l1_agree_final':0,'l1_compared_to_final':0});adjudicated=0
    for c in cases:
        trail=c.get('review_trail',[])
        if not trail:continue
        final=max(trail,key=lambda r:LEVEL[r['level']]);adjudicated+=1;incident=c.get('outcome',{}).get('post_merge_status') in {'incident','regression'};by={r['level']:r for r in trail}
        cls='random_audit' if any(x in {'random_audit_l1_selected','random_audit_l2_selected'} for x in c.get('labels',[])) else 'policy_escalation';sampling[cls]['cases']+=1
        for r in trail:
            d=per[r['level']];d['reviews']+=1;key=(r.get('model') or {}).get('family','human')+'@'+(r.get('model') or {}).get('version','n/a');model[key]['reviews']+=1;wkey=r.get('worker_command_digest') or 'unknown';worker[wkey]['reviews']+=1
            if LEVEL[r['level']]<LEVEL[final['level']]:
                d['compared_to_final']+=1;model[key]['compared_to_final']+=1;worker[wkey]['compared_to_final']+=1
                if r['verdict']==final['verdict']:d['agree_final']+=1;model[key]['agree_final']+=1;worker[wkey]['agree_final']+=1
                if r['level']=='L1':sampling[cls]['l1_compared_to_final']+=1;sampling[cls]['l1_agree_final']+=int(r['verdict']==final['verdict'])
            if r['level']=='L1':sampling[cls]['l1_reviews']+=1
            if incident and r['verdict']=='PASS':d['pass_then_incident']+=1
        for a,b in [('L1','L2'),('L2','ADVERSARIAL'),('ADVERSARIAL','HUMAN')]:
            if a in by and b in by and by[a]['verdict']!=by[b]['verdict']:reversals[f'{a}_TO_{b}']+=1
    for d in list(per.values())+list(model.values())+list(worker.values()):d['agreement_rate']=safe_div(d['agree_final'],d['compared_to_final'])
    for d in sampling.values():d['l1_agreement_rate']=safe_div(d['l1_agree_final'],d['l1_compared_to_final'])
    cfg=load_yaml(ns.limits).get('calibration',{});every=int(cfg.get('review_every_runs',500))
    out={'schema_version':'2.4','cases_seen':len(cases),'invalid_or_unanchored_cases':invalid,'cases_with_review':adjudicated,'per_level':dict(per),'per_model':dict(model),'per_worker_command':dict(worker),'sampling_strata':dict(sampling),'reversals':dict(reversals),'calibration_policy':{'review_every_runs':every,'review_due':len(cases)>=every,'completed_windows':(len(cases)//every if every>0 else 0),'metrics':cfg.get('metrics',[])},'interpretation':'Agreement is measured against the highest recorded authority, not assumed ground truth. Random-audit and policy-escalated strata are separated. Invalid/unanchored cases are surfaced, never silently discarded.'}
    Path(ns.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(ns.output)
if __name__=='__main__':main()
