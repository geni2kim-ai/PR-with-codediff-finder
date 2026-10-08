from __future__ import annotations
import argparse,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
from common import object_digest,sha256_file,write_json
from verify_manifest import manifest_entries

HEX_HEAD=re.compile(r'^[0-9a-f]{40,64}$')
HEX256=re.compile(r'^[0-9a-f]{64}ALLOWED={'schema_version','kind','authority_effect','head_sha','package_name','package_sha256','manifest_sha256','manifest_entries','clean_extract_verified','canonical_validation_passed','receipt_digest'}


def create(package,manifest,head_sha,*,clean_extract_verified,canonical_validation_passed):
    package=Path(package);manifest=Path(manifest)
    head_sha=str(head_sha).lower()
    if not package.is_file():raise ValueError('source package missing')
    if not manifest.is_file():raise ValueError('source package manifest missing')
    if not HEX_HEAD.fullmatch(head_sha):raise ValueError('invalid source package head_sha')
    entries=manifest_entries(manifest)
    obj={'schema_version':'2.7','kind':'source-package-receipt','authority_effect':'NONE',
         'head_sha':head_sha,'package_name':package.name,'package_sha256':sha256_file(package),
         'manifest_sha256':sha256_file(manifest),'manifest_entries':len(entries),
         'clean_extract_verified':bool(clean_extract_verified),
         'canonical_validation_passed':bool(canonical_validation_passed),'receipt_digest':''}
    obj['receipt_digest']=object_digest(obj,'receipt_digest')
    return obj


def validate(obj,package=None,manifest=None):
    e=[]
    if not isinstance(obj,dict):return ['source package receipt must be an object']
    if set(obj)!=ALLOWED:e.append('source package receipt fields mismatch')
    if obj.get('schema_version')!='2.7':e.append('source package receipt schema mismatch')
    if obj.get('kind')!='source-package-receipt':e.append('source package receipt kind mismatch')
    if obj.get('authority_effect')!='NONE':e.append('source package receipt authority_effect must be NONE')
    if not HEX_HEAD.fullmatch(str(obj.get('head_sha',''))):e.append('source package receipt head_sha invalid')
    if not isinstance(obj.get('package_name'),str) or not PACKAGE_NAME.fullmatch(obj['package_name']) or Path(obj['package_name']).name!=obj['package_name']:e.append('source package receipt package_name invalid')
    for k in ('package_sha256','manifest_sha256','receipt_digest'):
        if not HEX256.fullmatch(str(obj.get(k,''))):e.append(f'source package receipt {k} invalid')
    if not isinstance(obj.get('manifest_entries'),int) or obj.get('manifest_entries',0)<1:e.append('source package receipt manifest_entries invalid')
    if obj.get('clean_extract_verified') is not True:e.append('source package receipt clean_extract_verified must be true')
    if obj.get('canonical_validation_passed') is not True:e.append('source package receipt canonical_validation_passed must be true')
    if obj.get('receipt_digest')!=object_digest(obj,'receipt_digest'):e.append('source package receipt digest mismatch')
    if package is not None:
        p=Path(package)
        if not p.is_file():e.append('source package missing')
        else:
            if p.name!=obj.get('package_name'):e.append('source package name mismatch')
            if sha256_file(p)!=obj.get('package_sha256'):e.append('source package sha256 mismatch')
    if manifest is not None:
        p=Path(manifest)
        if not p.is_file():e.append('source package manifest missing')
        else:
            if sha256_file(p)!=obj.get('manifest_sha256'):e.append('source package manifest sha256 mismatch')
            try:
                if len(manifest_entries(p))!=obj.get('manifest_entries'):e.append('source package manifest entry count mismatch')
            except Exception as exc:e.append(f'source package manifest invalid: {type(exc).__name__}')
    return e


def main():
    ap=argparse.ArgumentParser(description='Create or verify an external digest receipt for a validated source ZIP')
    sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create');c.add_argument('--package',required=True);c.add_argument('--manifest',required=True);c.add_argument('--head-sha',required=True);c.add_argument('--output',required=True);c.add_argument('--clean-extract-verified',action='store_true');c.add_argument('--canonical-validation-passed',action='store_true')
    v=sub.add_parser('validate');v.add_argument('--receipt',required=True);v.add_argument('--package');v.add_argument('--manifest')
    ns=ap.parse_args()
    if ns.cmd=='create':
        obj=create(ns.package,ns.manifest,ns.head_sha,clean_extract_verified=ns.clean_extract_verified,canonical_validation_passed=ns.canonical_validation_passed)
        write_json(ns.output,obj);print(ns.output);return
    obj=json.loads(Path(ns.receipt).read_text(encoding='utf-8'));errs=validate(obj,ns.package,ns.manifest)
    if errs:print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
    print('VALID')


if __name__=='__main__':main()
)
PACKAGE_NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,255}ALLOWED={'schema_version','kind','authority_effect','head_sha','package_name','package_sha256','manifest_sha256','manifest_entries','clean_extract_verified','canonical_validation_passed','receipt_digest'}


def create(package,manifest,head_sha,*,clean_extract_verified,canonical_validation_passed):
    package=Path(package);manifest=Path(manifest)
    head_sha=str(head_sha).lower()
    if not package.is_file():raise ValueError('source package missing')
    if not manifest.is_file():raise ValueError('source package manifest missing')
    if not HEX_HEAD.fullmatch(head_sha):raise ValueError('invalid source package head_sha')
    entries=manifest_entries(manifest)
    obj={'schema_version':'2.7','kind':'source-package-receipt','authority_effect':'NONE',
         'head_sha':head_sha,'package_name':package.name,'package_sha256':sha256_file(package),
         'manifest_sha256':sha256_file(manifest),'manifest_entries':len(entries),
         'clean_extract_verified':bool(clean_extract_verified),
         'canonical_validation_passed':bool(canonical_validation_passed),'receipt_digest':''}
    obj['receipt_digest']=object_digest(obj,'receipt_digest')
    return obj


def validate(obj,package=None,manifest=None):
    e=[]
    if not isinstance(obj,dict):return ['source package receipt must be an object']
    if set(obj)!=ALLOWED:e.append('source package receipt fields mismatch')
    if obj.get('schema_version')!='2.7':e.append('source package receipt schema mismatch')
    if obj.get('kind')!='source-package-receipt':e.append('source package receipt kind mismatch')
    if obj.get('authority_effect')!='NONE':e.append('source package receipt authority_effect must be NONE')
    if not HEX_HEAD.fullmatch(str(obj.get('head_sha',''))):e.append('source package receipt head_sha invalid')
    if not isinstance(obj.get('package_name'),str) or Path(obj['package_name']).name!=obj['package_name']:e.append('source package receipt package_name invalid')
    for k in ('package_sha256','manifest_sha256','receipt_digest'):
        if not HEX256.fullmatch(str(obj.get(k,''))):e.append(f'source package receipt {k} invalid')
    if not isinstance(obj.get('manifest_entries'),int) or obj.get('manifest_entries',0)<1:e.append('source package receipt manifest_entries invalid')
    if obj.get('clean_extract_verified') is not True:e.append('source package receipt clean_extract_verified must be true')
    if obj.get('canonical_validation_passed') is not True:e.append('source package receipt canonical_validation_passed must be true')
    if obj.get('receipt_digest')!=object_digest(obj,'receipt_digest'):e.append('source package receipt digest mismatch')
    if package is not None:
        p=Path(package)
        if not p.is_file():e.append('source package missing')
        else:
            if p.name!=obj.get('package_name'):e.append('source package name mismatch')
            if sha256_file(p)!=obj.get('package_sha256'):e.append('source package sha256 mismatch')
    if manifest is not None:
        p=Path(manifest)
        if not p.is_file():e.append('source package manifest missing')
        else:
            if sha256_file(p)!=obj.get('manifest_sha256'):e.append('source package manifest sha256 mismatch')
            try:
                if len(manifest_entries(p))!=obj.get('manifest_entries'):e.append('source package manifest entry count mismatch')
            except Exception as exc:e.append(f'source package manifest invalid: {type(exc).__name__}')
    return e


def main():
    ap=argparse.ArgumentParser(description='Create or verify an external digest receipt for a validated source ZIP')
    sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create');c.add_argument('--package',required=True);c.add_argument('--manifest',required=True);c.add_argument('--head-sha',required=True);c.add_argument('--output',required=True);c.add_argument('--clean-extract-verified',action='store_true');c.add_argument('--canonical-validation-passed',action='store_true')
    v=sub.add_parser('validate');v.add_argument('--receipt',required=True);v.add_argument('--package');v.add_argument('--manifest')
    ns=ap.parse_args()
    if ns.cmd=='create':
        obj=create(ns.package,ns.manifest,ns.head_sha,clean_extract_verified=ns.clean_extract_verified,canonical_validation_passed=ns.canonical_validation_passed)
        write_json(ns.output,obj);print(ns.output);return
    obj=json.loads(Path(ns.receipt).read_text(encoding='utf-8'));errs=validate(obj,ns.package,ns.manifest)
    if errs:print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
    print('VALID')


if __name__=='__main__':main()
)
ALLOWED={'schema_version','kind','authority_effect','head_sha','package_name','package_sha256','manifest_sha256','manifest_entries','clean_extract_verified','canonical_validation_passed','receipt_digest'}


def create(package,manifest,head_sha,*,clean_extract_verified,canonical_validation_passed):
    package=Path(package);manifest=Path(manifest)
    head_sha=str(head_sha).lower()
    if not package.is_file():raise ValueError('source package missing')
    if not manifest.is_file():raise ValueError('source package manifest missing')
    if not HEX_HEAD.fullmatch(head_sha):raise ValueError('invalid source package head_sha')
    entries=manifest_entries(manifest)
    obj={'schema_version':'2.7','kind':'source-package-receipt','authority_effect':'NONE',
         'head_sha':head_sha,'package_name':package.name,'package_sha256':sha256_file(package),
         'manifest_sha256':sha256_file(manifest),'manifest_entries':len(entries),
         'clean_extract_verified':bool(clean_extract_verified),
         'canonical_validation_passed':bool(canonical_validation_passed),'receipt_digest':''}
    obj['receipt_digest']=object_digest(obj,'receipt_digest')
    return obj


def validate(obj,package=None,manifest=None):
    e=[]
    if not isinstance(obj,dict):return ['source package receipt must be an object']
    if set(obj)!=ALLOWED:e.append('source package receipt fields mismatch')
    if obj.get('schema_version')!='2.7':e.append('source package receipt schema mismatch')
    if obj.get('kind')!='source-package-receipt':e.append('source package receipt kind mismatch')
    if obj.get('authority_effect')!='NONE':e.append('source package receipt authority_effect must be NONE')
    if not HEX_HEAD.fullmatch(str(obj.get('head_sha',''))):e.append('source package receipt head_sha invalid')
    if not isinstance(obj.get('package_name'),str) or Path(obj['package_name']).name!=obj['package_name']:e.append('source package receipt package_name invalid')
    for k in ('package_sha256','manifest_sha256','receipt_digest'):
        if not HEX256.fullmatch(str(obj.get(k,''))):e.append(f'source package receipt {k} invalid')
    if not isinstance(obj.get('manifest_entries'),int) or obj.get('manifest_entries',0)<1:e.append('source package receipt manifest_entries invalid')
    if obj.get('clean_extract_verified') is not True:e.append('source package receipt clean_extract_verified must be true')
    if obj.get('canonical_validation_passed') is not True:e.append('source package receipt canonical_validation_passed must be true')
    if obj.get('receipt_digest')!=object_digest(obj,'receipt_digest'):e.append('source package receipt digest mismatch')
    if package is not None:
        p=Path(package)
        if not p.is_file():e.append('source package missing')
        else:
            if p.name!=obj.get('package_name'):e.append('source package name mismatch')
            if sha256_file(p)!=obj.get('package_sha256'):e.append('source package sha256 mismatch')
    if manifest is not None:
        p=Path(manifest)
        if not p.is_file():e.append('source package manifest missing')
        else:
            if sha256_file(p)!=obj.get('manifest_sha256'):e.append('source package manifest sha256 mismatch')
            try:
                if len(manifest_entries(p))!=obj.get('manifest_entries'):e.append('source package manifest entry count mismatch')
            except Exception as exc:e.append(f'source package manifest invalid: {type(exc).__name__}')
    return e


def main():
    ap=argparse.ArgumentParser(description='Create or verify an external digest receipt for a validated source ZIP')
    sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create');c.add_argument('--package',required=True);c.add_argument('--manifest',required=True);c.add_argument('--head-sha',required=True);c.add_argument('--output',required=True);c.add_argument('--clean-extract-verified',action='store_true');c.add_argument('--canonical-validation-passed',action='store_true')
    v=sub.add_parser('validate');v.add_argument('--receipt',required=True);v.add_argument('--package');v.add_argument('--manifest')
    ns=ap.parse_args()
    if ns.cmd=='create':
        obj=create(ns.package,ns.manifest,ns.head_sha,clean_extract_verified=ns.clean_extract_verified,canonical_validation_passed=ns.canonical_validation_passed)
        write_json(ns.output,obj);print(ns.output);return
    obj=json.loads(Path(ns.receipt).read_text(encoding='utf-8'));errs=validate(obj,ns.package,ns.manifest)
    if errs:print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
    print('VALID')


if __name__=='__main__':main()
