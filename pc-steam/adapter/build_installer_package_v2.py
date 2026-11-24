#!/usr/bin/env python3
"""Build the two-target, hash-bound Korean patch release directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


SOURCE_NAMES = (
    "PatchCommon.ps1",
    "Install-KoreanPatch.ps1",
    "Recover-KoreanPatch.ps1",
    "Restore-KoreanPatch.ps1",
    "Verify-KoreanPatch.ps1",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source_dir", type=Path)
    ap.add_argument("data_candidate", type=Path)
    ap.add_argument("exe_candidate", type=Path)
    ap.add_argument("candidate_qa", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()

    for name in SOURCE_NAMES:
        if not (args.source_dir / name).is_file():
            raise FileNotFoundError(args.source_dir / name)
    qa = load(args.candidate_qa)
    if qa.get("status") != "PASS" or qa.get("installed_to_game") is not False:
        raise ValueError("candidate QA is not an approved pre-install PASS")
    data_hash = sha256(args.data_candidate)
    exe_hash = sha256(args.exe_candidate)
    if data_hash != qa["candidate_data_jp_sha256"]:
        raise ValueError("data candidate hash changed")
    if exe_hash != qa["patched_exe_sha256"]:
        raise ValueError("executable candidate hash changed")

    baseline_data = Path(qa["baseline_data_jp"])
    baseline_exe = Path(qa["baseline_exe"])
    if sha256(baseline_data) != qa["baseline_data_jp_sha256"]:
        raise ValueError("trusted data baseline hash changed")
    if sha256(baseline_exe) != qa["baseline_exe_sha256"]:
        raise ValueError("trusted executable baseline hash changed")

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing release: {args.output}")
    args.output.mkdir(parents=True)
    for name in SOURCE_NAMES:
        shutil.copy2(args.source_dir / name, args.output / name)
    payload_dir = args.output / "payload"
    payload_dir.mkdir()
    payload_data = payload_dir / "data_jp.dat"
    payload_exe = payload_dir / "steam_criminal.exe"
    shutil.copy2(args.data_candidate, payload_data)
    shutil.copy2(args.exe_candidate, payload_exe)
    if payload_data.samefile(args.data_candidate) or payload_exe.samefile(args.exe_candidate):
        raise ValueError("payloads must be independent copies")

    readme = """Criminal Girls Invite Only 한국어 패치 v8

지원 대상
- 일본판 원본 data/data_jp.dat 및 steam_criminal.exe의 SHA-256이 manifest.json과 정확히 일치하는 설치본
- 번역 의미 기준: 일본어판
- 번역 및 일괄 검수: Codex 내부 모델

포함 내용
- 시나리오, 메뉴, 시스템 문구, 이미지 UI 한국어화
- 한글 폰트 및 한국어 이름 입력
- 이름 입력은 물리 키보드에서 표준 두벌식 한글 조합을 지원합니다.
- 한/영 키로 한글과 영문 입력을 전환합니다. 한/영 키가 IME에 잡히는 키보드에서는 F1로도 전환할 수 있습니다. Shift 영문 대문자와 숫자 0~9를 지원하며, 영문·숫자는 일본어 이름창 규격에 맞는 전각 문자로 저장됩니다.
- 원판에서 Q/E는 입력 커서 좌/우 이동이지만 직접 입력 중에는 이동 명령을 억제해 q/e가 문자로 입력됩니다.
- 화면 아래 글자판은 일본어 원판의 히라가나/가타카나 선택기를 그대로 유지합니다.
- 화면 아래 안내는 F1 한/영, Backspace 삭제, Ctrl 완료만 표시하며 원판의 오래된 L/I/Q/E 조작 아이콘은 제거했습니다.

패키지/게임 상태 검사
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-KoreanPatch.ps1 -GameRoot "게임 폴더"

설치
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "P:\백업 폴더"

중단된 설치 또는 복원 회수
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Recover-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "설치 때 사용한 P:\백업 폴더"

원본 복원
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Restore-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "설치 때 사용한 P:\백업 폴더"

설치·복원·복구 전에 대상 경로의 steam_criminal.exe를 종료해야 합니다.
BackupRoot는 게임 폴더와 패키지 폴더 바깥에 지정하십시오.
두 파일 중 하나만 바뀐 혼합 상태, 해시가 다른 파일, 손상된 패키지·백업은 쓰기 전에 거부됩니다.
"""
    (args.output / "README_KO.txt").write_text(readme, encoding="utf-8")

    roles = {
        "PatchCommon.ps1": "shared multi-target installer functions",
        "Install-KoreanPatch.ps1": "transactional two-target installer",
        "Recover-KoreanPatch.ps1": "interrupted-transaction recovery",
        "Restore-KoreanPatch.ps1": "transactional two-target restorer",
        "Verify-KoreanPatch.ps1": "read-only package and game verifier",
        "README_KO.txt": "Korean instructions",
        "payload/data_jp.dat": "patched Japanese-slot archive",
        "payload/steam_criminal.exe": "patched executable with Korean literals, Hangul-key toggled Korean/English/digit input, and the original Japanese selector",
    }
    files = []
    for rel, role in roles.items():
        path = args.output / Path(rel)
        files.append({"path": rel, "role": role, "size": path.stat().st_size, "sha256": sha256(path)})

    targets = [
        {
            "id": "data_jp",
            "relative_path": "data/data_jp.dat",
            "payload_path": "payload/data_jp.dat",
            "backup_name": "data_jp.dat",
            "baseline_size": baseline_data.stat().st_size,
            "baseline_sha256": qa["baseline_data_jp_sha256"],
            "patched_size": args.data_candidate.stat().st_size,
            "patched_sha256": data_hash,
        },
        {
            "id": "executable",
            "relative_path": "steam_criminal.exe",
            "payload_path": "payload/steam_criminal.exe",
            "backup_name": "steam_criminal.exe",
            "baseline_size": baseline_exe.stat().st_size,
            "baseline_sha256": qa["baseline_exe_sha256"],
            "patched_size": args.exe_candidate.stat().st_size,
            "patched_sha256": exe_hash,
        },
    ]
    counts = qa["counts"]
    manifest = {
        "schema": "criminal-girls-invite-only.ko-patch.v2",
        "patch_version": "jp-final-v8",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "semantic_source_language": "ja-JP",
        "translation_model": "Codex internal model",
        "installed_to_game": False,
        "game": {"executable_relative_path": "steam_criminal.exe", "targets": targets},
        "coverage": {
            "non_bscr_rows": counts["non_bscr_rows"],
            "bscr_occurrences": counts["bscr_occurrences"],
            "exe_literals": counts["exe_literals"],
            "localized_ui_logical_assets": counts["localized_ui_logical_assets"],
            "localized_ui_archive_entries": counts["localized_ui_archive_entries"],
            "standard_wansung_syllables": 2350,
            "name_input_mode": "Hangul press-event or F1 toggled Korean two-set + CP932 fullwidth English/digits 0-9 + original Japanese on-screen selector",
            "name_help_legend": "F1 한/영 / Backspace 삭제 / Ctrl 완료 / Enter 선택한 일본어 입력",
        },
        "files": files,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    actual = sorted(p.relative_to(args.output).as_posix() for p in args.output.rglob("*") if p.is_file())
    expected = sorted(["manifest.json", *roles])
    if actual != expected or len(actual) != 9:
        raise ValueError({"actual": actual, "expected": expected})
    for item in files:
        path = args.output / item["path"]
        if path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
            raise ValueError(f"post-manifest mismatch: {item['path']}")

    report = {
        "schema": "criminal-girls.installer-package-build.v2",
        "status": "PASS",
        "package": str(args.output),
        "allowlisted_files": len(actual),
        "payload_link_mode": "independent_copy",
        "payloads": {
            "data_jp": {"size": payload_data.stat().st_size, "sha256": sha256(payload_data)},
            "executable": {"size": payload_exe.stat().st_size, "sha256": sha256(payload_exe)},
        },
        "manifest_sha256": sha256(manifest_path),
        "installed_to_game": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

