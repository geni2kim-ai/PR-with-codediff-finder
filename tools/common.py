from __future__ import annotations
import hashlib, json, re
from pathlib import Path


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def object_digest(obj, digest_field: str | None = None) -> str:
    if digest_field and isinstance(obj, dict):
        obj={k:v for k,v in obj.items() if k != digest_field}
    return sha256_bytes(canonical_bytes(obj))


def canonical_finding_path(path, changed_paths=None) -> str:
    """Return a stable repository-relative identity for reviewer finding paths.

    Git paths are POSIX-style and backslash may be a literal filename character,
    so backslashes are never rewritten to '/'. A leading './' is accepted only as
    a presentation alias. Absolute/traversal spellings are rejected.
    """
    if not isinstance(path,str) or not path:
        raise ValueError("finding path must be a non-empty string")
    changed=set(changed_paths or [])
    candidate=path
    while candidate.startswith("./"):
        candidate=candidate[2:]
    if "\x00" in candidate:
        raise ValueError("finding path contains NUL")
    if candidate.startswith("/"):
        raise ValueError("finding path must be repository-relative")
    parts=candidate.split("/")
    if not candidate or any(part in {"",".",".."} for part in parts):
        raise ValueError("finding path contains unsafe repository segments")
    # Exact task paths are authoritative Git identities, even if their literal
    # filename happens to resemble a Windows host path.
    if path in changed:
        return path
    if candidate in changed:
        return candidate
    if candidate.startswith("\\\\") or re.match(r"^[A-Za-z]:[\\/]",candidate):
        raise ValueError("finding path must not be a host absolute path")
    return candidate


def named_files_digest(entries) -> str:
    """Bind both logical identity and bytes of referenced files.

    entries may be (logical_name, path) tuples. Missing files are rejected rather than
    silently collapsing to the same digest as an empty ref set.
    """
    rows=[]
    for logical,path in entries:
        p=Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"required referenced file missing: {logical} -> {p}")
        rows.append({"ref":str(logical).replace('\\','/'),"sha256":sha256_file(p)})
    rows.sort(key=lambda r:r['ref'])
    return sha256_bytes(canonical_bytes(rows))


def write_json(path: str | Path, obj) -> None:
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
