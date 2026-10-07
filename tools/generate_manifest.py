from __future__ import annotations
import argparse,hashlib,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--git-ref',default='HEAD');ap.add_argument('--output',required=True);ns=ap.parse_args()
    paths=[p for p in subprocess.check_output(['git','-C',str(ROOT),'ls-tree','-r','--name-only',ns.git_ref],text=True).splitlines() if p and p!='MANIFEST.sha256']
    rows=[]
    for p in sorted(paths):
        data=subprocess.check_output(['git','-C',str(ROOT),'show',f'{ns.git_ref}:{p}'])
        rows.append(f"{hashlib.sha256(data).hexdigest()}  ./{p}")
    Path(ns.output).write_text('\n'.join(rows)+'\n',encoding='utf-8')
    print(f'generated {len(rows)} manifest entries -> {ns.output}')
if __name__=='__main__':main()
