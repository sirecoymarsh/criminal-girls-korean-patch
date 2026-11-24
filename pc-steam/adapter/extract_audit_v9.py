from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path)
    ap.add_argument("zip_path", type=Path)
    ap.add_argument("extract_root", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()

    package = args.package.resolve()
    zip_path = args.zip_path.resolve()
    extract_root = args.extract_root.resolve()
    if extract_root.exists():
        raise FileExistsError(extract_root)

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8-sig"))
    rels = sorted({"manifest.json", *(str(row["path"]).replace("\\", "/") for row in manifest["files"])})
    if len(rels) != 9:
        raise ValueError("release allowlist must contain exactly nine files")
    root_name = "CriminalGirlsInviteOnly_KoreanPatch_v9"
    wanted = [f"{root_name}/{rel}" for rel in rels]
    with zipfile.ZipFile(zip_path, "r", allowZip64=True) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if sorted(names) != sorted(wanted) or len(infos) != 9 or archive.testzip() is not None:
            raise ValueError("ZIP member allowlist/CRC mismatch")
        for name in names:
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != root_name or any(part in {"", ".", ".."} for part in parts):
                raise ValueError(f"unsafe ZIP member: {name}")
        archive.extractall(extract_root)

    extracted = extract_root / root_name
    actual = sorted(p.relative_to(extracted).as_posix() for p in extracted.rglob("*") if p.is_file())
    files = []
    for rel in rels:
        source = package / rel
        target = extracted / rel
        present = target.is_file()
        row = {
            "path": rel,
            "present": present,
            "size": target.stat().st_size if present else None,
            "sha256": sha256(target) if present else None,
        }
        row["ok"] = present and row["size"] == source.stat().st_size and row["sha256"] == sha256(source)
        files.append(row)
    delta = sorted(set(actual).symmetric_difference(rels))
    status = "PASS" if not delta and all(row["ok"] for row in files) else "FAIL"
    report = {
        "schema": "criminal-girls.release-zip-extraction-audit.v9",
        "status": status,
        "zip": str(zip_path),
        "zip_size": zip_path.stat().st_size,
        "zip_sha256": sha256(zip_path),
        "extracted_package": str(extracted),
        "file_count": len(actual),
        "allowlist_delta": delta,
        "files": files,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
