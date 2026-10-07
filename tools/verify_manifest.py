from __future__ import annotations
import argparse,hashlib,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def git_bytes(ref,path):
    return subprocess.check_output(['git','-C',str(ROOT),'show',f'{ref}:{path}'])

def git_paths(ref):
    out=subprocess.check_output(['git','-C',str(ROOT),'ls-tree','-r','--name-only',ref],text=True)
    return {x for x in out.splitlines() if x and x!='MANIFEST.sha256'}

def manifest_entries(path):
    entries={}
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        if not raw.strip():continue
        expected,rel=raw.split('  ',1);rel=rel.removeprefix('./')
        if rel in entries:raise ValueError(f'duplicate manifest path: {rel}')
        entries[rel]=expected.lower()
    return entries

def errors(manifest='MANIFEST.sha256',ref='HEAD'):
    m=manifest_entries(ROOT/manifest);tree=git_paths(ref);e=[]
    for p in sorted(tree-set(m)):e.append(f'unmanifested Git blob: {p}')
    for p in sorted(set(m)-tree):e.append(f'manifest entry not in Git tree: {p}')
    for p,expected in sorted(m.items()):
        if p not in tree:continue
        actual=hashlib.sha256(git_bytes(ref,p)).hexdigest()
        if actual!=expected:e.append(f'hash mismatch: ./{p}')
    return e,len(m)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',default='MANIFEST.sha256');ap.add_argument('--git-ref',default='HEAD');ns=ap.parse_args()
    e,n=errors(ns.manifest,ns.git_ref)
    if e:raise SystemExit('\n'.join(e))
    print(f'MANIFEST Git-blob verification: PASS ({n} entries)')
if __name__=='__main__':main()
