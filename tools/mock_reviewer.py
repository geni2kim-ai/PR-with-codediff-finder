from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from common import object_digest
from sanitize_review_text import scan_stage_result

def finding(fid='F-001',severity='major',family='MOCK-MAJOR',axis='correctness_security'):
    return {'finding_id':fid,'axis':axis,'severity':severity,'confidence':'high','certainty':'confirmed','path':'src/example.py','line':1,'claim':'Mock defect detected','evidence':'Changed branch violates the test fixture expectation','source_ref':'fixture','impact':'The fixture models a review failure','recommendation':'Correct the fixture or implementation','preexisting':False,'activated_or_worsened':True,'failure_family':family}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',default='pass');ns=ap.parse_args();task=json.load(sys.stdin);level=task['level'];c=task['reviewer_contract']
    findings=[];verdict='PASS';confidence='high';target='NONE';requested=False;novel=False
    risk={'reversibility':'EASY','blast_radius':'LOCAL','data_sensitivity':'NONE','security_surface':'LOW','availability_criticality':'LOW'}
    if ns.mode=='major': findings=[finding()];verdict='FINDINGS'
    elif ns.mode=='minor': findings=[finding(severity='minor',family='MOCK-MINOR')];verdict='FINDINGS'
    elif ns.mode=='low': confidence='low'
    elif ns.mode=='novel': findings=[finding(family='NOVEL-MOCK')];verdict='FINDINGS';novel=True;requested=True;target='ADVERSARIAL'
    elif ns.mode=='block': verdict='BLOCKED'
    elif ns.mode=='security-high': findings=[finding(family='SECURITY-CRITICAL')];verdict='FINDINGS';risk['security_surface']='HIGH';requested=True;target='HUMAN'
    elif ns.mode=='human-risk': risk['reversibility']='HARD';requested=True;target='HUMAN'
    elif ns.mode=='unsafe-url': findings=[finding(severity='minor',family='MOCK-UNSAFE')];findings[0]['source_ref']='www.example.invalid/leak';verdict='FINDINGS'
    elif ns.mode=='unsafe-mention': findings=[finding(severity='minor',family='MOCK-UNSAFE')];findings[0]['failure_family']='ALERT-\u200b@owner';verdict='FINDINGS'
    elif ns.mode=='mutate-head':
        import subprocess
        repo=task['binding']['workspace_ref'];Path(repo,'reviewer_mutation.txt').write_text('mutation\n');subprocess.run(['git','add','reviewer_mutation.txt'],cwd=repo,check=True);subprocess.run(['git','-c','user.email=mock@example.com','-c','user.name=mock','commit','-qm','reviewer mutation'],cwd=repo,check=True)
    elif ns.mode=='dirty-worktree':
        repo=Path(task['binding']['workspace_ref']);target=repo/'src/a.py';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(target.read_text()+'# reviewer dirty\n' if target.exists() else '# reviewer dirty\n')
    elif ns.mode=='sleep-pass':
        time.sleep(0.8)
    elif ns.mode=='exit-fail':
        print('mock reviewer failed',file=sys.stderr);raise SystemExit(7)
    elif ns.mode=='huge-output':
        sys.stdout.write('X'*(2*1024*1024));return
    elif ns.mode=='huge-stderr':
        sys.stderr.write('E'*(2*1024*1024));sys.stderr.flush();return
    o={'schema_version':'2.4','task_id':task['task_id'],'case_id':task['case_id'],'level':level,'binding':{'repository':task['binding']['repository'],'reviewed_head_sha':task['binding']['head_sha']},'evidence_digest':task['sensor']['evidence_digest'],'reviewer':{**c,'independent_context':level in {'L2','ADVERSARIAL'}},'verdict':verdict,'confidence':confidence,'findings':findings,'risk_signal':risk,'escalation':{'requested':requested,'target':target,'reasons':['MOCK_ESCALATION'] if requested else [],'novel_failure_family':novel},'output_safety':{'sanitized':True,'external_urls_present':False,'markdown_images_present':False,'mentions_present':False,'secret_scan_passed':True},'result_digest':''}
    o['output_safety']=scan_stage_result(o)
    o['result_digest']=object_digest(o,'result_digest');json.dump(o,sys.stdout,ensure_ascii=False)
if __name__=='__main__':main()
