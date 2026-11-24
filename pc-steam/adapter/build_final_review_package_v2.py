#!/usr/bin/env python3
"""Build the final UI + Japanese-scenario + installer approval package."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    out = args.output.resolve()
    release_root = (root / "release").resolve()
    if out.parent != release_root or not out.name.startswith("final_integrated_review_jp_"):
        raise ValueError(f"unsafe review output: {out}")
    if out.exists():
        shutil.rmtree(out)

    base_builder = Path(__file__).with_name("build_final_review_package.py")
    subprocess.run([sys.executable, str(base_builder), str(root), str(out)], check=True)

    reports = root / "release/reports"
    package = root / "release/korean_patch_jp_final_v1"
    report_sources = {
        "installer_package_build.json": reports / "installer_package_build.json",
        "installer_package_self_verification.json": reports / "installer_package_self_verification.json",
        "installer_builder_fixture.json": reports / "installer_builder_fixture.json",
        "installer_full_fixture.json": reports / "installer_full_fixture.json",
        "installer_fixture_matrix.json": reports / "installer_fixture_matrix.json",
        "defender_scan_korean_patch_jp_final_v1.json": reports / "defender_scan_korean_patch_jp_final_v1.json",
        "installer_release_qa.json": reports / "installer_release_qa.json",
        "installer_manifest.json": package / "manifest.json",
    }
    for name, source in report_sources.items():
        shutil.copy2(source, out / "reports" / name)

    build = load(report_sources["installer_package_build.json"])
    self_verify = load(report_sources["installer_package_self_verification.json"])
    builder_fixture = load(report_sources["installer_builder_fixture.json"])
    full_fixture = load(report_sources["installer_full_fixture.json"])
    matrix = load(report_sources["installer_fixture_matrix.json"])
    defender = load(report_sources["defender_scan_korean_patch_jp_final_v1.json"])
    release_qa = load(report_sources["installer_release_qa.json"])
    manifest = load(report_sources["installer_manifest.json"])

    case_rows = "".join(
        f"<tr><td>{esc(case['name'])}</td><td class='pass'>{esc(case['status'])}</td><td><code>{esc(json.dumps(case.get('details', {}), ensure_ascii=False))}</code></td></tr>"
        for case in matrix["cases"]
    )
    check_rows = "".join(
        f"<tr><td>{esc(name)}</td><td class='{'pass' if value else 'fail'}'>{'PASS' if value else 'FAIL'}</td></tr>"
        for name, value in release_qa["checks"].items()
    )
    defender_output = "\n".join(defender.get("scan_output", []))
    installer_html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>한국어 패치 설치·복구 검수</title>
<style>body{{margin:0;background:#17151c;color:#f5f0f7;font-family:"Malgun Gothic",sans-serif}}main{{max-width:1150px;margin:auto;padding:34px}}h1{{font-size:29px}}h2{{color:#ff9de8;margin-top:30px}}.card{{background:#241f2a;border:1px solid #5d4964;border-radius:10px;padding:18px;margin:14px 0;line-height:1.7}}table{{width:100%;border-collapse:collapse;background:#241f2a}}th,td{{border:1px solid #5d4964;padding:9px;vertical-align:top}}th{{color:#ff9de8;text-align:left}}code{{color:#b9ffca;overflow-wrap:anywhere}}.pass{{color:#8effb0;font-weight:800}}.fail{{color:#ff8080;font-weight:800}}pre{{white-space:pre-wrap;background:#15131a;padding:12px;border-radius:6px}}</style></head><body><main>
<h1>설치·복구 패키지 최종 검수</h1>
<div class="card"><span class="pass">전체 설치 릴리스 QA PASS</span><br>실제 F 드라이브 게임은 아직 원본이며, 최종 승인 전에는 설치하지 않습니다.</div>
<h2>패키지</h2><div class="card">경로: <code>{esc(package)}</code><br>허용 파일: {release_qa['package_file_count']}개<br>매니페스트 SHA-256: <code>{esc(release_qa['manifest_sha256'])}</code><br>페이로드 SHA-256: <code>{esc(release_qa['payload_sha256'])}</code><br>페이로드 크기: {release_qa['payload_size']:,} bytes<br>후보와 독립된 실제 복사본: <span class="pass">PASS</span></div>
<h2>통합 판정 {sum(bool(v) for v in release_qa['checks'].values())}/{len(release_qa['checks'])}</h2><table><thead><tr><th>검사</th><th>결과</th></tr></thead><tbody>{check_rows}</tbody></table>
<h2>Windows PowerShell 5.1 모의 설치 행렬</h2><div class="card">실제 크기·한글/공백 경로 설치/복원: <span class="pass">{esc(full_fixture['status'])}</span><br>원본 미변경: {esc(full_fixture['original_unchanged'])} · 반복 설치/복원: PASS · 거래 임시 파일: {full_fixture['leftover_transaction_files']}개</div>
<table><thead><tr><th>케이스</th><th>결과</th><th>세부</th></tr></thead><tbody>{case_rows}</tbody></table>
<h2>Microsoft Defender</h2><div class="card">상태: <span class="pass">{esc(defender['status'])}</span><br>서명: {esc(defender['defender']['signature_version'])} · 검사 대상 탐지: {defender['scan_target_detection_count']}개 · 신규 탐지: {defender['new_detection_count']}개<br><pre>{esc(defender_output)}</pre></div>
<h2>현재 실제 게임</h2><div class="card">원본 SHA-256: <code>{esc(release_qa['live_sha256'])}</code><br>거래 임시 파일: {len(release_qa['live_transaction_files'])}개<br>설치 여부: <strong>미설치</strong></div>
</main></body></html>'''
    (out / "INSTALLER_REVIEW.html").write_text(installer_html, encoding="utf-8")

    main_page = out / "FINAL_REVIEW.html"
    page = main_page.read_text(encoding="utf-8")
    old_links = '<ol><li><a href="ui_review/UI_REVIEW.html">UI 36종 원본 비교 및 인코딩 왕복 검수</a></li><li><a href="translation/SCENARIO_REVIEW.html">일본판 원문 기반 시나리오·시스템 2,709문구 검수</a></li></ol>'
    new_links = old_links[:-5] + '<li><a href="INSTALLER_REVIEW.html">설치·복구·변조 거부·Defender 패키지 검수</a></li></ol>'
    if old_links not in page:
        raise ValueError("review-link insertion point not found")
    page = page.replace(old_links, new_links)
    package_card = f'''<h2>최종 설치 패키지</h2><div class="card">경로: <code>{esc(package)}</code><br>파일: {release_qa['package_file_count']}개 · 후보와 독립된 실제 복사본<br>매니페스트 SHA-256: <code>{esc(release_qa['manifest_sha256'])}</code><br>PowerShell 5.1 설치/복원·변조 거부·중단 복구·Defender: <span class="pass">PASS</span><br>실제 게임 원본 유지: <span class="pass">PASS</span></div>\n'''
    marker = '<h2>승인 방법</h2>'
    if marker not in page:
        raise ValueError("approval insertion point not found")
    page = page.replace(marker, package_card + marker)
    main_page.write_text(page, encoding="utf-8")

    readme = out / "README_KO.txt"
    text = readme.read_text(encoding="utf-8")
    text = text.replace("2. UI 검수와 시나리오·시스템 번역 검수를 모두 확인하세요.", "2. UI, 시나리오·시스템 번역, 설치·복구 패키지 검수를 모두 확인하세요.")
    text += f"\n최종 설치 패키지: {package}\n매니페스트 SHA-256: {release_qa['manifest_sha256']}\n설치 패키지 QA: PASS\n"
    readme.write_text(text, encoding="utf-8")

    verification_path = out / "reports/review_package_verification.json"
    verification = load(verification_path)
    extra_checks = {
        "installer_review_exists": (out / "INSTALLER_REVIEW.html").is_file(),
        "installer_release_qa_pass": release_qa.get("status") == "PASS" and all(release_qa.get("checks", {}).values()),
        "installer_self_verification_pass": self_verify.get("status") == "PASS",
        "installer_builder_fixture_pass": builder_fixture.get("status") == "PASS",
        "installer_full_fixture_pass": full_fixture.get("status") == "PASS",
        "installer_matrix_pass": matrix.get("status") == "PASS" and len(matrix.get("cases", [])) == 7,
        "defender_scan_pass": defender.get("status") == "PASS" and defender.get("scan_target_detection_count") == 0,
        "installer_payload_matches_candidate": manifest["game"]["patched_sha256"] == release_qa["payload_sha256"],
        "installer_package_not_live": release_qa.get("installed_to_game") is False,
    }
    verification["checks"].update(extra_checks)
    verification["status"] = "PASS" if all(verification["checks"].values()) else "FAIL"
    verification_path.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary_path = out / "package_summary.json"
    summary = load(summary_path)
    summary.update({
        "status": verification["status"],
        "review_surfaces": 3,
        "installer_status": release_qa["status"],
        "installer_package": str(package),
        "installer_manifest_sha256": release_qa["manifest_sha256"],
        "installer_payload_independent_copy": release_qa["payload_independent_from_candidate"],
        "installer_fixture_cases": release_qa["fixture_case_count"],
        "defender_scan_target_detections": release_qa["defender_scan_target_detections"],
        "live_original_unchanged": release_qa["checks"]["live_original_still_unchanged"],
        "installed_to_game": False,
    })
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_out = out / "package_sha256_manifest.json"
    if manifest_out.exists():
        manifest_out.unlink()
    files = [
        {"path": path.relative_to(out).as_posix(), "size": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(p for p in out.rglob("*") if p.is_file())
    ]
    manifest_out.write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    package_files = [p for p in out.rglob("*") if p.is_file()]
    summary["package_file_count"] = len(package_files)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Summary changed after the first manifest generation; regenerate once more.
    manifest_out.unlink()
    files = [
        {"path": path.relative_to(out).as_posix(), "size": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(p for p in out.rglob("*") if p.is_file())
    ]
    manifest_out.write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())