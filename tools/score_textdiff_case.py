from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from policy_engine import load_yaml
from validate_rsi_evaluation import derive

def main():
    ap=argparse.ArgumentParser(description='Recompute v2.4 RSI score/promotion from a candidate record')
    ap.add_argument('json');ap.add_argument('--policy',default=str(ROOT/'policy/rsi-scoring.yml'));ns=ap.parse_args()
    o=json.loads(Path(ns.json).read_text(encoding='utf-8'));overall,p=derive(o,load_yaml(ns.policy));print(json.dumps({'overall_score':overall,'promotion':p},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
