from __future__ import annotations

import argparse
import os
import re
import subprocess
import zipfile
from pathlib import PurePosixPath

ENTRY_RE = re.compile(rb"^([0-9]{6}) (blob) ([0-9a-f]{40,64})\t(.*)$")


def _git(repo, args, *, binary=False):
    cp = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
        check=False,
    )
    if cp.returncode:
        err = cp.stderr.decode("utf-8", "replace") if binary else cp.stderr
        raise RuntimeError(err[-2000:])
    return cp.stdout


def tree_entries(repo, ref):
    raw = _git(repo, ["ls-tree", "-r", "-z", ref], binary=True)
    entries = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        m = ENTRY_RE.match(record)
        if not m:
            raise ValueError("unsupported Git tree entry")
        mode = m.group(1).decode("ascii")
        path = m.group(4).decode("utf-8", "strict")
        p = PurePosixPath(path)
        if (
            not path
            or "\\" in path
            or p.is_absolute()
            or any(part in {"", ".", ".."} for part in p.parts)
        ):
            raise ValueError(f"unsafe Git package path: {path}")
        if mode not in {"100644", "100755"}:
            raise ValueError(f"unsupported Git mode for source package: {mode} {path}")
        entries.append((mode, path))
    return entries


def blob_bytes(repo, ref, path):
    return _git(repo, ["show", f"{ref}:{path}"], binary=True)


def build(repo, ref, output, prefix):
    output = os.fspath(output)
    if not prefix or not prefix.endswith("/"):
        raise ValueError("package prefix must be non-empty and end with /")
    entries = tree_entries(repo, ref)
    if not entries:
        raise ValueError("Git tree is empty")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for mode, path in entries:
            info = zipfile.ZipInfo(prefix + path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            perms = 0o755 if mode == "100755" else 0o644
            info.external_attr = (perms & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, blob_bytes(repo, ref, path), compresslevel=9)
    return len(entries)


def main():
    ap = argparse.ArgumentParser(
        description="Build a deterministic ZIP directly from exact Git blob bytes"
    )
    ap.add_argument("--repo", default=".")
    ap.add_argument("--git-ref", default="HEAD")
    ap.add_argument("--output", required=True)
    ap.add_argument("--prefix", default="PR-with-codediff-finder-v2.7/")
    ns = ap.parse_args()
    try:
        count = build(ns.repo, ns.git_ref, ns.output, ns.prefix)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise SystemExit(str(exc))
    print(f"built {count} exact Git blobs -> {ns.output}")


if __name__ == "__main__":
    main()
