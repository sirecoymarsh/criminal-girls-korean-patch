#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def hash_stream(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hash_stream(stream)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()
    package = args.package.resolve()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8-sig"))
    expected = {"manifest.json", *[str(row["path"]).replace("\\", "/") for row in manifest["files"]]}
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()}
    if actual != expected or len(actual) != 9:
        raise ValueError({"expected": sorted(expected), "actual": sorted(actual)})
    root_name = "CriminalGirlsInviteOnly_KoreanPatch_v8"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for rel in sorted(actual):
            archive.write(package / rel, f"{root_name}/{rel}")
    disk_hashes = {rel: sha256(package / rel) for rel in sorted(actual)}
    zip_hashes = {}
    with zipfile.ZipFile(args.output, "r", allowZip64=True) as archive:
        infos = archive.infolist()
        names = {info.filename for info in infos}
        wanted_names = {f"{root_name}/{rel}" for rel in actual}
        if names != wanted_names or len(infos) != 9 or archive.testzip() is not None:
            raise ValueError("ZIP member/CRC verification failed")
        for rel in sorted(actual):
            with archive.open(f"{root_name}/{rel}", "r") as stream:
                zip_hashes[rel] = hash_stream(stream)
    mismatches = [rel for rel in sorted(actual) if zip_hashes[rel] != disk_hashes[rel]]
    report = {
        "schema": "criminal-girls.release-zip.v8",
        "status": "PASS" if not mismatches else "FAIL",
        "package": str(package),
        "zip": str(args.output),
        "zip_size": args.output.stat().st_size,
        "zip_sha256": sha256(args.output),
        "zip_member_count": len(actual),
        "zip64": args.output.stat().st_size >= 0xFFFFFFFF or any((package / rel).stat().st_size >= 0xFFFFFFFF for rel in actual),
        "compression": "stored",
        "exact_member_allowlist": True,
        "all_member_hashes_match_package": not mismatches,
        "mismatches": mismatches,
        "members": [
            {"path": rel, "size": (package / rel).stat().st_size, "sha256": disk_hashes[rel]}
            for rel in sorted(actual)
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "members"}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
