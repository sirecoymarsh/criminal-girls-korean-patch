#!/usr/bin/env python3
"""Create and independently inspect a deterministic stored ZIP from the v2 release."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_stream(stream) -> str:
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
        h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("package", type=Path)
    ap.add_argument("zip_path", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()
    package = args.package.resolve()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "criminal-girls-invite-only.ko-patch.v2":
        raise ValueError("not a v2 release manifest")
    rels = ["manifest.json", *[str(x["path"]).replace("\\", "/") for x in manifest["files"]]]
    if len(rels) != 9 or len(set(rels)) != 9:
        raise ValueError("release must contain exactly nine unique files")
    actual = sorted(p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file())
    if actual != sorted(rels):
        raise ValueError({"actual": actual, "expected": sorted(rels)})
    if args.zip_path.exists():
        raise FileExistsError(f"refusing to overwrite ZIP: {args.zip_path}")
    args.zip_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "CriminalGirlsInviteOnly_KoreanPatch_v2"
    source = {}
    with zipfile.ZipFile(args.zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for rel in rels:
            path = package / rel
            digest = sha256_file(path)
            source[rel] = {"size": path.stat().st_size, "sha256": digest}
            zi = zipfile.ZipInfo(f"{prefix}/{rel}", date_time=(2026, 8, 13, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED
            zi.create_system = 3
            zi.external_attr = (stat.S_IFREG | 0o644) << 16
            zi.flag_bits |= 0x800
            with path.open("rb") as src, zf.open(zi, "w", force_zip64=True) as dst:
                for block in iter(lambda: src.read(8 * 1024 * 1024), b""):
                    dst.write(block)

    members = []
    with zipfile.ZipFile(args.zip_path, "r", allowZip64=True) as zf:
        names = zf.namelist()
        expected_names = [f"{prefix}/{rel}" for rel in rels]
        if names != expected_names:
            raise ValueError({"zip_names": names, "expected": expected_names})
        for rel, name in zip(rels, names):
            info = zf.getinfo(name)
            with zf.open(info, "r") as stream:
                digest = sha256_stream(stream)
            ok = info.file_size == source[rel]["size"] and digest == source[rel]["sha256"]
            if not ok:
                raise ValueError(f"ZIP member mismatch: {rel}")
            members.append(
                {
                    "path": rel,
                    "zip_path": name,
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                    "sha256": digest,
                    "ok": ok,
                }
            )
    result = {
        "schema": "criminal-girls.release-zip.v2",
        "status": "PASS",
        "package": str(package),
        "package_manifest_sha256": sha256_file(package / "manifest.json"),
        "zip": str(args.zip_path),
        "zip_size": args.zip_path.stat().st_size,
        "zip_sha256": sha256_file(args.zip_path),
        "compression": "stored",
        "member_count": len(members),
        "members": members,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "members"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
