from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from common import object_digest, sha256_file, write_json
from verify_manifest import manifest_entries

HEX_HEAD = re.compile(r"^[0-9a-f]{40,64}$")
HEX256 = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
ALLOWED = {
    "schema_version",
    "kind",
    "authority_effect",
    "head_sha",
    "package_name",
    "package_sha256",
    "manifest_sha256",
    "manifest_entries",
    "clean_extract_verified",
    "canonical_validation_passed",
    "validation_run_id",
    "validation_run_attempt",
    "validation_workflow_ref",
    "receipt_digest",
}


def create(package, manifest, head_sha, *, clean_extract_verified, canonical_validation_passed, validation_run_id=None, validation_run_attempt=None, validation_workflow_ref=None):
    package = Path(package)
    manifest = Path(manifest)
    head_sha = str(head_sha).lower()
    if not package.is_file():
        raise ValueError("source package missing")
    if not manifest.is_file():
        raise ValueError("source package manifest missing")
    if not HEX_HEAD.fullmatch(head_sha):
        raise ValueError("invalid source package head_sha")
    if not PACKAGE_NAME.fullmatch(package.name):
        raise ValueError("invalid source package name")
    entries = manifest_entries(manifest)
    obj = {
        "schema_version": "2.7",
        "kind": "source-package-receipt",
        "authority_effect": "NONE",
        "head_sha": head_sha,
        "package_name": package.name,
        "package_sha256": sha256_file(package),
        "manifest_sha256": sha256_file(manifest),
        "manifest_entries": len(entries),
        "clean_extract_verified": bool(clean_extract_verified),
        "canonical_validation_passed": bool(canonical_validation_passed),
        "validation_run_id": int(validation_run_id) if validation_run_id not in {None,""} else None,
        "validation_run_attempt": int(validation_run_attempt) if validation_run_attempt not in {None,""} else None,
        "validation_workflow_ref": str(validation_workflow_ref) if validation_workflow_ref not in {None,""} else None,
        "receipt_digest": "",
    }
    obj["receipt_digest"] = object_digest(obj, "receipt_digest")
    return obj


def validate(obj, package=None, manifest=None):
    errors = []
    if not isinstance(obj, dict):
        return ["source package receipt must be an object"]
    if set(obj) != ALLOWED:
        errors.append("source package receipt fields mismatch")
    if obj.get("schema_version") != "2.7":
        errors.append("source package receipt schema mismatch")
    if obj.get("kind") != "source-package-receipt":
        errors.append("source package receipt kind mismatch")
    if obj.get("authority_effect") != "NONE":
        errors.append("source package receipt authority_effect must be NONE")
    if not HEX_HEAD.fullmatch(str(obj.get("head_sha", ""))):
        errors.append("source package receipt head_sha invalid")
    package_name = obj.get("package_name")
    if (
        not isinstance(package_name, str)
        or not PACKAGE_NAME.fullmatch(package_name)
        or Path(package_name).name != package_name
    ):
        errors.append("source package receipt package_name invalid")
    for key in ("package_sha256", "manifest_sha256", "receipt_digest"):
        if not HEX256.fullmatch(str(obj.get(key, ""))):
            errors.append(f"source package receipt {key} invalid")
    if type(obj.get("manifest_entries")) is not int or obj.get("manifest_entries", 0) < 1:
        errors.append("source package receipt manifest_entries invalid")
    if obj.get("clean_extract_verified") is not True:
        errors.append("source package receipt clean_extract_verified must be true")
    if obj.get("canonical_validation_passed") is not True:
        errors.append("source package receipt canonical_validation_passed must be true")
    run_id=obj.get("validation_run_id");run_attempt=obj.get("validation_run_attempt");workflow_ref=obj.get("validation_workflow_ref")
    if run_id is not None and (type(run_id) is not int or run_id<1):
        errors.append("source package receipt validation_run_id invalid")
    if run_attempt is not None and (type(run_attempt) is not int or run_attempt<1):
        errors.append("source package receipt validation_run_attempt invalid")
    if workflow_ref is not None and (not isinstance(workflow_ref,str) or not workflow_ref or len(workflow_ref)>512):
        errors.append("source package receipt validation_workflow_ref invalid")
    if (run_id is None)!=(run_attempt is None):
        errors.append("source package receipt validation run id/attempt must be provided together")
    if obj.get("receipt_digest") != object_digest(obj, "receipt_digest"):
        errors.append("source package receipt digest mismatch")

    if package is not None:
        package_path = Path(package)
        if not package_path.is_file():
            errors.append("source package missing")
        else:
            if package_path.name != package_name:
                errors.append("source package name mismatch")
            if sha256_file(package_path) != obj.get("package_sha256"):
                errors.append("source package sha256 mismatch")

    if manifest is not None:
        manifest_path = Path(manifest)
        if not manifest_path.is_file():
            errors.append("source package manifest missing")
        else:
            if sha256_file(manifest_path) != obj.get("manifest_sha256"):
                errors.append("source package manifest sha256 mismatch")
            try:
                if len(manifest_entries(manifest_path)) != obj.get("manifest_entries"):
                    errors.append("source package manifest entry count mismatch")
            except Exception as exc:
                errors.append(f"source package manifest invalid: {type(exc).__name__}")
    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Create or verify an external digest receipt for a validated source ZIP"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--package", required=True)
    create_parser.add_argument("--manifest", required=True)
    create_parser.add_argument("--head-sha", required=True)
    create_parser.add_argument("--output", required=True)
    create_parser.add_argument("--clean-extract-verified", action="store_true")
    create_parser.add_argument("--canonical-validation-passed", action="store_true")
    create_parser.add_argument("--validation-run-id",default=os.environ.get("GITHUB_RUN_ID"))
    create_parser.add_argument("--validation-run-attempt",default=os.environ.get("GITHUB_RUN_ATTEMPT"))
    create_parser.add_argument("--validation-workflow-ref",default=os.environ.get("GITHUB_WORKFLOW_REF"))

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--receipt", required=True)
    validate_parser.add_argument("--package")
    validate_parser.add_argument("--manifest")

    ns = parser.parse_args()
    if ns.cmd == "create":
        obj = create(
            ns.package,
            ns.manifest,
            ns.head_sha,
            clean_extract_verified=ns.clean_extract_verified,
            canonical_validation_passed=ns.canonical_validation_passed,
            validation_run_id=ns.validation_run_id,
            validation_run_attempt=ns.validation_run_attempt,
            validation_workflow_ref=ns.validation_workflow_ref,
        )
        write_json(ns.output, obj)
        print(ns.output)
        return

    obj = json.loads(Path(ns.receipt).read_text(encoding="utf-8"))
    errors = validate(obj, ns.package, ns.manifest)
    if errors:
        print("INVALID")
        for error in errors:
            print("-", error)
        raise SystemExit(1)
    print("VALID")


if __name__ == "__main__":
    main()
