from __future__ import annotations
import argparse,hashlib,os,re,stat,subprocess
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
SHA256_RE=re.compile(r'^[0-9a-fA-F]{64}$')


def git_bytes(ref,path):
    return subprocess.check_output(['git','-C',str(ROOT),'show',f'{ref}:{path}'])


def git_paths(ref):
    out=subprocess.check_output(['git','-C',str(ROOT),'ls-tree','-r','--name-only',ref],text=True)
    return {x for x in out.splitlines() if x and x!='MANIFEST.sha256'}


def _safe_rel(rel):
    raw=rel.removeprefix('./')
    if not raw or '\\' in raw or '\x00' in raw:
        raise ValueError(f'unsafe manifest path: {rel}')
    p=PurePosixPath(raw)
    if p.is_absolute() or any(x in {'','.','..'} for x in p.parts):
        raise ValueError(f'unsafe manifest path: {rel}')
    return p.as_posix()


def manifest_entries(path):
    entries={}
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        if not raw.strip():continue
        if '  ' not in raw:raise ValueError(f'invalid manifest row: {raw[:120]}')
        expected,rel=raw.split('  ',1)
        if not SHA256_RE.fullmatch(expected):raise ValueError(f'invalid manifest sha256: {expected}')
        rel=_safe_rel(rel)
        if rel=='MANIFEST.sha256':raise ValueError('MANIFEST.sha256 must not self-index')
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


def _filesystem_entries(root):
    root=Path(root).resolve();out={}
    if not root.is_dir():raise ValueError(f'filesystem root missing: {root}')
    def walk(d):
        for ent in os.scandir(d):
            p=Path(ent.path);rel=p.relative_to(root).as_posix()
            if rel=='MANIFEST.sha256':continue
            mode=ent.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                walk(p);continue
            if stat.S_ISLNK(mode):
                target=os.readlink(p)
                data=os.fsencode(target)
            elif stat.S_ISREG(mode):
                data=p.read_bytes()
            else:
                raise ValueError(f'unsupported filesystem entry: {rel}')
            out[rel]=hashlib.sha256(data).hexdigest()
    walk(root)
    return out


def filesystem_errors(manifest='MANIFEST.sha256',filesystem_root=None):
    root=Path(filesystem_root or ROOT).resolve()
    manifest_path=Path(manifest)
    if not manifest_path.is_absolute():manifest_path=root/manifest_path
    m=manifest_entries(manifest_path);actual=_filesystem_entries(root);e=[]
    for p in sorted(set(actual)-set(m)):e.append(f'unmanifested package file: {p}')
    for p in sorted(set(m)-set(actual)):e.append(f'manifested package file missing: {p}')
    for p,expected in sorted(m.items()):
        if p in actual and actual[p]!=expected:e.append(f'package hash mismatch: ./{p}')
    return e,len(m)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',default='MANIFEST.sha256')
    ap.add_argument('--git-ref',default='HEAD')
    ap.add_argument('--filesystem-root',help='verify an extracted package tree without requiring .git metadata')
    ns=ap.parse_args()
    try:
        if ns.filesystem_root:e,n=filesystem_errors(ns.manifest,ns.filesystem_root)
        else:e,n=errors(ns.manifest,ns.git_ref)
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))
    if e:raise SystemExit('\n'.join(e))
    if ns.filesystem_root:print(f'MANIFEST filesystem verification: PASS ({n} entries)')
    else:print(f'MANIFEST Git-blob verification: PASS ({n} entries)')


if __name__=='__main__':main()
