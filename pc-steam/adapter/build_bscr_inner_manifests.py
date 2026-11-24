#!/usr/bin/env python3
"""Build hash-bound DSARCIDX inner replacement manifests for BSCR v2 payloads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bscr_common import discover_payloads, sha256_file, write_json
from dsarcidx_tool import read_entries


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_CONTAINERS = PROJECT / "extracted" / "map_scripts" / "jp" / "containers"
DEFAULT_PAYLOADS = PROJECT / "translation" / "bscr_v2" / "injected_payloads"
DEFAULT_OUTPUT = PROJECT / "translation" / "bscr_v2" / "inner_manifests"
DEFAULT_AUDIT = PROJECT / "audit" / "bscr_v2_inner_manifests.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-root", type=Path, default=DEFAULT_CONTAINERS)
    parser.add_argument("--payload-root", type=Path, default=DEFAULT_PAYLOADS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    payloads = discover_payloads(args.payload_root)
    containers = {path.name: path for path in sorted(args.container_root.glob("map_d_*.tpk"))}
    errors: list[dict] = []
    manifests: list[dict] = []
    args.output_root.mkdir(parents=True, exist_ok=True)

    for logical_name, payload_path in sorted(payloads.items()):
        parts = Path(logical_name).parts
        if len(parts) != 2:
            errors.append({"file": logical_name, "code": "unexpected_payload_path_shape"})
            continue
        container_name = parts[0] + ".tpk"
        expected_entry_name = parts[1]
        container_path = containers.get(container_name)
        if container_path is None:
            errors.append({"file": logical_name, "code": "missing_container", "container": container_name})
            continue
        entries, metadata = read_entries(container_path)
        matching = [entry for entry in entries if entry.name == expected_entry_name]
        if len(entries) != 1 or len(matching) != 1 or matching[0].index != 0:
            errors.append({
                "file": logical_name,
                "code": "unexpected_inner_archive_layout",
                "entry_count": len(entries),
                "matching_count": len(matching),
            })
            continue
        entry = matching[0]
        manifest = {
            "schema": "criminal-girls.bscr-inner-replacements.v2",
            "format": "DSARCIDX",
            "template": str(container_path),
            "template_sha256": sha256_file(container_path),
            "template_entry_count": len(entries),
            "replacements": [{
                "index": entry.index,
                "expected_name": entry.name,
                "expected_file_id": entry.file_id,
                "expected_original_size": entry.size,
                "path": str(payload_path),
                "replacement_size": payload_path.stat().st_size,
                "replacement_sha256": sha256_file(payload_path),
            }],
        }
        manifest_path = args.output_root / f"{container_name}.replacements.json"
        write_json(manifest_path, manifest)
        manifests.append({
            "container": container_name,
            "template": str(container_path),
            "template_sha256": manifest["template_sha256"],
            "manifest": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "payload": str(payload_path),
            "payload_sha256": manifest["replacements"][0]["replacement_sha256"],
            "entry": {
                "index": entry.index,
                "file_id": entry.file_id,
                "name": entry.name,
                "original_size": entry.size,
            },
            "archive_metadata": {
                "magic": metadata["magic"],
                "first_payload_offset": metadata["first_payload_offset"],
                "record_size": metadata["record_size"],
            },
        })

    extra_containers = sorted(set(containers) - {item["container"] for item in manifests})
    if extra_containers:
        errors.append({"code": "containers_without_payload", "containers": extra_containers})
    result = {
        "schema": "criminal-girls.bscr-inner-manifest-audit.v2",
        "pass": not errors and len(manifests) == 54,
        "container_count": len(containers),
        "payload_count": len(payloads),
        "manifest_count": len(manifests),
        "error_count": len(errors),
        "errors": errors,
        "manifests": manifests,
    }
    write_json(args.audit, result)
    print(json.dumps({
        "pass": result["pass"],
        "container_count": len(containers),
        "payload_count": len(payloads),
        "manifest_count": len(manifests),
        "error_count": len(errors),
        "audit": str(args.audit),
    }, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

