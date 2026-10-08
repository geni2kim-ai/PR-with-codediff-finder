from __future__ import annotations
import argparse,json,math,os,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_case_bundle import errors as bundle_errors
from policy_engine import load_yaml
LEVEL={'L1':1,'L2':2,'ADVERSARIAL':3,'HUMAN':4}
MACHINE_LEVELS={'L1','L2','ADVERSARIAL'}

def safe_div(a,b):return round(a/b,4) if b else None

def material_state(row):
    if row.get('level')=='HUMAN':return row.get('verdict')
    if row.get('verdict')=='BLOCKED':return 'BLOCKED'
    if 'material_finding_count' in row:return 'FINDINGS' if int(row.get('material_finding_count',0))>0 else 'PASS'
    return row.get('verdict')

def p95(values):
    if not values:return None
    rows=sorted(int(x) for x in values);return rows[max(0,math.ceil(len(rows)*0.95)-1)]

def summarize_cases(cases,cfg):
    per=defaultdict(lambda:{'reviews':0,'compared_to_final':0,'agree_final':0,'pass_then_incident':0})
    reversals=defaultdict(int);model=defaultdict(lambda:{'reviews':0,'compared_to_final':0,'agree_final':0});worker=defaultdict(lambda:{'reviews':0,'compared_to_final':0,'agree_final':0})
    sampling=defaultdict(lambda:{'cases':0,'l1_reviews':0,'l1_agree_final':0,'l1_compared_to_final':0})
    human={'decisions':0,'confirmed_parent':0,'rejected_parent':0,'parent_missing':0,'by_parent_level':defaultdict(lambda:{'confirmed':0,'rejected':0})}
    total_material=total_notes=total_major=total_blocker=0;l1_major_with_l2=l1_major_cleared=0
    note_keys=Counter();note_families=Counter();campaign_attempts=[];campaign_cases=0;same_repeat=0;budget_human=0;adjudicated=0
    for c in cases:
        trail=c.get('review_trail',[]);machine=[r for r in trail if r.get('level') in MACHINE_LEVELS]
        if not machine:continue
        final=max(machine,key=lambda r:LEVEL[r['level']]);adjudicated+=1;incident=c.get('outcome',{}).get('post_merge_status') in {'incident','regression'}
        by_level={r['level']:r for r in machine};by_id={r.get('review_id'):r for r in trail if r.get('review_id')}
        cls='random_audit' if any(x in {'random_audit_l1_selected','random_audit_l2_selected'} for x in c.get('labels',[])) else 'policy_escalation';sampling[cls]['cases']+=1
        case_note_keys=set();case_note_families=set()
        for r in trail:
            level=r.get('level');d=per[level];d['reviews']+=1;key=(r.get('model') or {}).get('family','human')+'@'+(r.get('model') or {}).get('version','n/a');model[key]['reviews']+=1;wkey=r.get('worker_command_digest') or 'unknown';worker[wkey]['reviews']+=1
            if level in MACHINE_LEVELS and LEVEL[level]<LEVEL[final['level']]:
                d['compared_to_final']+=1;model[key]['compared_to_final']+=1;worker[wkey]['compared_to_final']+=1;agree=material_state(r)==material_state(final)
                if agree:d['agree_final']+=1;model[key]['agree_final']+=1;worker[wkey]['agree_final']+=1
                if level=='L1':sampling[cls]['l1_compared_to_final']+=1;sampling[cls]['l1_agree_final']+=int(agree)
            if level=='L1':sampling[cls]['l1_reviews']+=1
            if level in MACHINE_LEVELS and incident and material_state(r)=='PASS':d['pass_then_incident']+=1
            total_material+=int(r.get('material_finding_count',0));total_notes+=int(r.get('note_only_finding_count',0));total_major+=int(r.get('major_finding_count',0));total_blocker+=int(r.get('blocker_finding_count',0))
            case_note_keys.update(r.get('note_only_finding_keys',[]) or []);case_note_families.update(r.get('note_only_finding_families',[]) or [])
            if level=='HUMAN':
                human['decisions']+=1;parent=by_id.get(r.get('parent_review_id'))
                if parent is None:human['parent_missing']+=1
                elif r.get('verdict')=='CONFIRMED':human['confirmed_parent']+=1;human['by_parent_level'][parent.get('level')]['confirmed']+=1
                elif r.get('verdict')=='REJECTED':human['rejected_parent']+=1;human['by_parent_level'][parent.get('level')]['rejected']+=1
        for k in case_note_keys:note_keys[k]+=1
        for fam in case_note_families:note_families[fam]+=1
        for a,b in [('L1','L2'),('L2','ADVERSARIAL')]:
            if a in by_level and b in by_level and material_state(by_level[a])!=material_state(by_level[b]):reversals[f'{a}_TO_{b}']+=1
        l1=by_level.get('L1');l2=by_level.get('L2')
        if l1 and l2 and int(l1.get('major_finding_count',0))>0:
            l1_major_with_l2+=1
            if material_state(l2)=='PASS':l1_major_cleared+=1
        camp=c.get('review_campaign')
        if isinstance(camp,dict):
            campaign_cases+=1;campaign_attempts.append(int(camp.get('attempt_index',1)))
            if camp.get('stop_reason')=='SAME_MATERIAL_FINDING_REPEAT':same_repeat+=1
            if camp.get('stop_reason') in {'SAME_MATERIAL_FINDING_REPEAT','AUTOMATED_ATTEMPT_LIMIT'}:budget_human+=1
    for d in list(per.values())+list(model.values())+list(worker.values()):d['agreement_rate']=safe_div(d['agree_final'],d['compared_to_final'])
    for d in sampling.values():d['l1_agreement_rate']=safe_div(d['l1_agree_final'],d['l1_compared_to_final'])
    recurring_min=int(cfg.get('recurring_note_min_occurrences',3))
    recurring_keys=[{'key':k,'case_occurrences':n} for k,n in sorted(note_keys.items(),key=lambda x:(-x[1],x[0])) if n>=recurring_min]
    recurring_families=[{'failure_family':k,'case_occurrences':n} for k,n in sorted(note_families.items(),key=lambda x:(-x[1],x[0])) if n>=recurring_min]
    human_out={'decisions':human['decisions'],'confirmed_parent':human['confirmed_parent'],'rejected_parent':human['rejected_parent'],'parent_missing':human['parent_missing'],'parent_confirmation_rate':safe_div(human['confirmed_parent'],human['confirmed_parent']+human['rejected_parent']),'by_parent_level':dict(human['by_parent_level'])}
    leonardo={'material_findings':total_material,'note_only_findings':total_notes,'major_findings':total_major,'blocker_findings':total_blocker,'note_only_rate':safe_div(total_notes,total_notes+total_material),
              'l1_major_cases_with_l2':l1_major_with_l2,'l1_major_cleared_by_l2':l1_major_cleared,'major_l2_downgrade_rate':safe_div(l1_major_cleared,l1_major_with_l2),
              'campaign_cases':campaign_cases,'automated_attempts_p95':p95(campaign_attempts),'same_material_repeat_rate':safe_div(same_repeat,campaign_cases),'review_budget_human_escalation_rate':safe_div(budget_human,campaign_cases),
              'recurring_note_min_occurrences':recurring_min,'recurring_note_keys':recurring_keys,'recurring_note_families':recurring_families}
    return {'cases_with_review':adjudicated,'per_level':dict(per),'per_model':dict(model),'per_worker_command':dict(worker),'sampling_strata':dict(sampling),'reversals':dict(reversals),'human_decisions':human_out,'leonardo_metrics':leonardo}

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
    cfg=load_yaml(ns.limits).get('calibration',{});every=int(cfg.get('review_every_runs',500));summary=summarize_cases(cases,cfg)
    out={'schema_version':'2.7','cases_seen':len(cases),'invalid_or_unanchored_cases':invalid,**summary,
         'calibration_policy':{'review_every_runs':every,'review_due':len(cases)>=every,'completed_windows':(len(cases)//every if every>0 else 0),'metrics':cfg.get('metrics',[])},
         'interpretation':'Machine-review agreement uses material finding state, so NOTE_ONLY does not count as a reversal. HUMAN CONFIRMED/REJECTED is reported as confirmation/rejection of its parent review rather than compared as a different verdict vocabulary. Recurring NOTE_ONLY keys are proposal signals only and do not auto-change standards.'}
    Path(ns.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(ns.output)
if __name__=='__main__':main()
