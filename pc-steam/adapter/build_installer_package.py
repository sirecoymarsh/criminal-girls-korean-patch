#!/usr/bin/env python3
"""Build a minimal hash-bound Korean patch directory from an allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source_dir", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("candidate_qa", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()

    source_names = (
        "PatchCommon.ps1",
        "Install-KoreanPatch.ps1",
        "Recover-KoreanPatch.ps1",
        "Restore-KoreanPatch.ps1",
        "Verify-KoreanPatch.ps1",
    )
    for name in source_names:
        if not (args.source_dir / name).is_file():
            raise FileNotFoundError(args.source_dir / name)
    qa = json.loads(args.candidate_qa.read_text(encoding="utf-8"))
    if qa.get("status") != "PASS" or qa.get("installed_to_game") is not False:
        raise ValueError("candidate QA is not an approved pre-install PASS")
    if sha256(args.candidate) != qa["candidate_sha256"]:
        raise ValueError("candidate hash changed")

    args.output.mkdir(parents=True, exist_ok=True)
    for name in source_names:
        shutil.copy2(args.source_dir / name, args.output / name)
    payload_dir = args.output / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    payload = payload_dir / "data_jp.dat"
    if payload.exists():
        payload.unlink()
    link_mode = "independent_copy"
    shutil.copy2(args.candidate, payload)

    readme = """Criminal Girls Invite Only 한국어 패치

지원 대상
- 일본판 data/data_jp.dat 원본 SHA-256이 매니페스트와 정확히 일치하는 설치본
- 의미 기준: 일본어 원문
- 번역·통합 검수: Codex 내부 모델

패키지 검사
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Verify-KoreanPatch.ps1

설치
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Install-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "P:\\백업 폴더"

중단된 설치나 복원
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Recover-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "설치 때 사용한 P:\\백업 폴더"

복원
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Restore-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "설치 때 사용한 P:\\백업 폴더"

설치 전 steam_criminal.exe를 종료해야 합니다.
BackupRoot는 게임 폴더와 이 패키지 폴더 바깥에 지정해야 합니다.
해시가 다른 게임 파일, 손상된 패키지 또는 손상된 백업은 쓰기 전에 거부됩니다.
"""
    (args.output / "README_KO.txt").write_text(readme, encoding="utf-8")

    roles = {
        "PatchCommon.ps1": "shared installer functions",
        "Install-KoreanPatch.ps1": "transactional installer",
        "Recover-KoreanPatch.ps1": "interrupted-transaction recovery",
        "Restore-KoreanPatch.ps1": "transactional restorer",
        "Verify-KoreanPatch.ps1": "read-only verifier",
        "README_KO.txt": "Korean instructions",
        "payload/data_jp.dat": "patched Japanese-slot game archive",
    }
    files = []
    for rel, role in roles.items():
        path = args.output / Path(rel)
        files.append({"path": rel, "role": role, "size": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "schema": "criminal-girls-invite-only.ko-patch.v1",
        "patch_version": "jp-final-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "semantic_source_language": "ja-JP",
        "translation_model": "Codex internal model",
        "installed_to_game": False,
        "game": {
            "executable_relative_path": "steam_criminal.exe",
            "data_relative_path": "data/data_jp.dat",
            "baseline_size": qa["baseline_size"],
            "baseline_sha256": qa["baseline_sha256"],
            "patched_size": qa["candidate_size"],
            "patched_sha256": qa["candidate_sha256"],
        },
        "payload": {"path": "payload/data_jp.dat"},
        "coverage": {
            "unique_strings": 2709,
            "translated_strings": 2637,
            "preserved_literals": 72,
            "translated_occurrences": 9153,
            "ui_audited": 36,
            "ui_localized": 26,
        },
        "files": files,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    actual = sorted(p.relative_to(args.output).as_posix() for p in args.output.rglob("*") if p.is_file())
    expected = sorted(["manifest.json", *roles])
    if actual != expected:
        raise ValueError({"actual": actual, "expected": expected})
    for item in files:
        path = args.output / item["path"]
        if path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
            raise ValueError(f"post-manifest mismatch: {item['path']}")

    report = {
        "status": "PASS",
        "package": str(args.output),
        "allowlisted_files": len(actual),
        "payload_link_mode": link_mode,
        "payload_size": payload.stat().st_size,
        "payload_sha256": sha256(payload),
        "manifest_sha256": sha256(args.output / "manifest.json"),
        "installed_to_game": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
