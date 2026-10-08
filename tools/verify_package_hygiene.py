from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath

CACHE_DIRS={".pytest_cache","__pycache__"}
CACHE_SUFFIXES={".pyc",".pyo"}


def generated_paths(paths):
    out=[]
    for raw in paths:
        path=str(raw).strip()
        if not path:
            continue
        p=PurePosixPath(path)
        if any(part in CACHE_DIRS for part in p.parts) or p.suffix.lower() in CACHE_SUFFIXES:
            out.append(path)
    return sorted(set(out))


def tracked_paths(ref="HEAD"):
    cp=subprocess.run(
        ["git","ls-tree","-r","--name-only",ref],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cp.returncode:
        raise RuntimeError(cp.stderr[-2000:])
    return [x for x in cp.stdout.splitlines() if x]


def main():
    ap=argparse.ArgumentParser(description="Reject tracked generated test/cache artifacts before packaging")
    ap.add_argument("--git-ref",default="HEAD")
    ns=ap.parse_args()
    try:
        bad=generated_paths(tracked_paths(ns.git_ref))
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    if bad:
        print("TRACKED_GENERATED_ARTIFACTS")
        for path in bad:
            print("-",path)
        raise SystemExit(1)
    print("PACKAGE HYGIENE: PASS")


if __name__=="__main__":
    main()
