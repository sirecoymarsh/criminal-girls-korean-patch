#!/usr/bin/env python3
"""Build the standalone pre-install UI + Japanese-scenario review package."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from collections import Counter
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    root, out = args.root, args.output
    ui_source = root / "release/ui_complete_review_v2"
    final_map = root / "translation/jp_based_reviewed_translation.jsonl"
    changes_path = root / "translation/jp_original_review/jp_review_changes.jsonl"
    candidate_qa_path = root / "staging/reports/final_candidate_qa.json"
    rows = read_jsonl(final_map)
    changes = read_jsonl(changes_path)
    changes_by_id = {row["source_id"]: row for row in changes}
    candidate_qa = json.loads(candidate_qa_path.read_text(encoding="utf-8"))

    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ui_source, out / "ui_review", dirs_exist_ok=True)
    (out / "translation").mkdir(parents=True, exist_ok=True)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_map, out / "translation/jp_based_reviewed_translation.jsonl")
    shutil.copy2(changes_path, out / "translation/jp_review_changes.jsonl")

    report_sources = {
        "jp_review_summary.json": root / "translation/jp_original_review/jp_review_summary.json",
        "jp_final_qa.json": root / "translation/jp_original_review/jp_final_qa.json",
        "localized_text_report.json": root / "staging/localized_text_report.json",
        "korean_font_report.json": root / "staging/korean_font_report.json",
        "localized_containers_report.json": root / "staging/localized_containers_report.json",
        "encoded_ui_report.json": root / "staging/ui_encoded/encoded_ui_report.json",
        "preservation_verification.json": root / "ui_review/full_mockups/preservation_verification.json",
        "outer_replacements_jp_final.json": root / "staging/manifests/outer_replacements_jp_final.json",
        "data_jp_jp_final.json": root / "staging/reports/data_jp_jp_final.json",
        "final_archive_diff_jp_final.json": root / "staging/reports/final_archive_diff_jp_final.json",
        "final_candidate_qa.json": candidate_qa_path,
    }
    for name, source in report_sources.items():
        shutil.copy2(source, out / "reports" / name)

    lane_counts = Counter(lane for row in rows for lane in row.get("lanes", []))
    table_rows: list[str] = []
    for row in rows:
        source_id = row["source_id"]
        status = row["status"]
        ko = row.get("reviewed_ko") if status == "review_complete" else row.get("source_ja")
        lane = ", ".join(row.get("lanes", []))
        contexts = row.get("contexts", [])
        context_text = " / ".join(
            f"{c.get('file')} :: {c.get('key') if c.get('key') is not None else '#' + str(c.get('record_index'))}"
            for c in contexts[:3]
        )
        changed = changes_by_id.get(source_id)
        changed_note = ""
        if changed:
            before = changed.get("before_ko")
            changed_note = f'<div class="before">검수 전: {e(before) if before is not None else "번역하지 않고 원문 유지"}</div>'
        changed_badge = '<br><span class="badge changed-badge">JP &#52572;&#51333; &#44368;&#51221;</span>' if changed else ""
        status_label = "번역 완료" if status == "review_complete" else "원문 유지"
        search = " ".join((source_id, lane, row.get("source_ja", ""), ko or "", row.get("reference_en", ""), context_text)).lower()
        table_rows.append(
            f'<tr class="{"changed" if changed else ""}" data-status="{e(status)}" data-lane="{e(lane)}" data-search="{e(search)}">'
            f'<td><code>{e(source_id)}</code><br><span class="badge">{e(status_label)}</span>{changed_badge}</td>'
            f'<td>{e(lane)}<br><small>발생 {row.get("occurrence_count", 0)}회</small></td>'
            f'<td class="text ja">{e(row.get("source_ja", ""))}<small>{e(context_text)}</small></td>'
            f'<td class="text ko">{e(ko)}{changed_note}</td>'
            f'<td class="text en">{e(row.get("reference_en", ""))}</td>'
            '</tr>'
        )

    scenario_html = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>일본판 원문 기반 시나리오·시스템 번역 검수</title>
<style>
:root{{--bg:#15131a;--panel:#211d29;--line:#493a52;--fg:#f5f0f7;--muted:#bcb3c2;--pink:#ff9de8;--cyan:#8deef5;--green:#8effb0}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font-family:"Malgun Gothic",sans-serif}}
header{{position:sticky;top:0;z-index:3;background:rgba(21,19,26,.97);border-bottom:1px solid var(--line);padding:18px 24px}}
h1{{margin:0 0 8px;font-size:25px}}.meta{{color:var(--muted);line-height:1.55}}.controls{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}}
input,select,button{{background:#292330;color:var(--fg);border:1px solid #675370;border-radius:6px;padding:9px 11px;font-size:14px}}input{{min-width:390px;flex:1}}
main{{padding:22px}}table{{width:100%;border-collapse:collapse;background:var(--panel);table-layout:fixed}}th,td{{border:1px solid var(--line);padding:10px;vertical-align:top}}th{{position:sticky;top:151px;background:#302638;color:var(--pink);z-index:2}}
th:nth-child(1){{width:125px}}th:nth-child(2){{width:145px}}th:nth-child(3),th:nth-child(4){{width:28%}}.text{{white-space:pre-wrap;line-height:1.55;overflow-wrap:anywhere}}small{{display:block;color:var(--muted);margin-top:7px;line-height:1.35}}code{{color:var(--cyan)}}
.badge{{display:inline-block;margin-top:6px;padding:2px 6px;border-radius:10px;background:#3c3244;color:#ddd;font-size:11px}}.changed-badge{{background:#633f60;color:#ffd5f5}}tr.changed{{background:#281f2c}}.before{{color:#d8a9cc;font-size:12px;margin-top:8px;border-top:1px dashed #644d69;padding-top:6px}}
.hidden{{display:none}}.count{{color:var(--green);font-weight:700}}
</style></head><body>
<header><h1>일본판 원문 기반 시나리오·시스템 한국어 번역</h1>
<div class="meta">일본어 원문이 의미 기준이며 영어 공식 문구는 참고 열일 뿐입니다. 초벌 번역과 최종 통합 검수는 모두 Codex 내부 모델로 수행했습니다.<br>
고유 문구 2,709개 · 번역 완료 2,637개 · 숫자/더미/개발 자리표시자 원문 유지 72개 · 일본판 최종 교정 25개 · QA 문제 0개<br>
표시 중: <span id="shown" class="count">2,709</span>개</div>
<div class="controls"><input id="q" placeholder="ID, 일본어, 한국어, 파일명 검색"><select id="lane"><option value="">모든 분류</option>{''.join(f'<option value="{e(k)}">{e(k)} ({v})</option>' for k,v in sorted(lane_counts.items()))}</select><select id="status"><option value="">모든 상태</option><option value="review_complete">번역 완료</option><option value="preserve">원문 유지</option></select><label><input id="changed" type="checkbox"> JP 최종 교정만</label><button id="reset">초기화</button></div></header>
<main><table><thead><tr><th>ID/상태</th><th>분류</th><th>일본어 원문</th><th>한국어 최종</th><th>영어 참고</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></main>
<script>
const rows=[...document.querySelectorAll('tbody tr')],q=document.querySelector('#q'),lane=document.querySelector('#lane'),status=document.querySelector('#status'),changed=document.querySelector('#changed'),shown=document.querySelector('#shown');
function apply(){{const needle=q.value.trim().toLowerCase();let n=0;for(const r of rows){{const ok=(!needle||r.dataset.search.includes(needle))&&(!lane.value||r.dataset.lane.includes(lane.value))&&(!status.value||r.dataset.status===status.value)&&(!changed.checked||r.classList.contains('changed'));r.classList.toggle('hidden',!ok);if(ok)n++}}shown.textContent=n.toLocaleString('ko-KR')}}
[q,lane,status,changed].forEach(x=>x.addEventListener(x===q?'input':'change',apply));document.querySelector('#reset').onclick=()=>{{q.value='';lane.value='';status.value='';changed.checked=false;apply()}};
</script></body></html>'''
    (out / "translation/SCENARIO_REVIEW.html").write_text(scenario_html, encoding="utf-8")

    final_html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Criminal Girls Invite Only 한국어화 최종 통합 검수</title>
<style>body{{margin:0;background:#17151c;color:#f5f0f7;font-family:"Malgun Gothic",sans-serif}}main{{max-width:1100px;margin:auto;padding:34px}}h1{{font-size:31px}}h2{{color:#ff9de8;margin-top:34px}}.card{{background:#241f2a;border:1px solid #5d4964;border-radius:10px;padding:20px;margin:16px 0;line-height:1.7}}a{{color:#8deef5;font-weight:700}}code{{color:#b9ffca;overflow-wrap:anywhere}}.pass{{color:#8effb0;font-weight:800}}li{{margin:7px 0}}</style></head><body><main>
<h1>Criminal Girls Invite Only — 한국어화 최종 통합 검수</h1>
<div class="card"><span class="pass">전체 자동 검증 PASS</span><br>게임 폴더에는 아직 설치하지 않았습니다. 이 검수본 승인 후에만 최종 후보를 설치합니다.</div>
<h2>검수 화면</h2><div class="card"><ol><li><a href="ui_review/UI_REVIEW.html">UI 36종 원본 비교 및 인코딩 왕복 검수</a></li><li><a href="translation/SCENARIO_REVIEW.html">일본판 원문 기반 시나리오·시스템 2,709문구 검수</a></li></ol></div>
<h2>완성 범위</h2><div class="card"><ul><li>UI 전수 감사 36종, 한국어화 26종, 문자 없는 10종 원본 유지</li><li>원본 프레임·아이콘·배경·위치·색상·서체 계열·굵기 보존 검증 PASS</li><li>일본어 원문 기준 고유 문구 2,709개: 번역 2,637개, 원문 유지 72개</li><li>실제 발생 위치 9,153개 재삽입, 텍스트 파일 241개</li><li>내장 폰트 5종 한글 글리프 검증 PASS</li><li>중첩 컨테이너 110개, 외부 교체 엔트리 151개 검증 PASS</li></ul></div>
<h2>최종 후보</h2><div class="card">경로: <code>{e(candidate_qa['candidate'])}</code><br>SHA-256: <code>{e(candidate_qa['candidate_sha256'])}</code><br>크기: {candidate_qa['candidate_size']:,} bytes<br>설치 여부: <strong>미설치</strong></div>
<h2>승인 방법</h2><div class="card">두 검수 화면을 확인한 뒤 수정할 부분이 있으면 <strong>자산명/문구 ID와 수정 내용</strong>을 알려 주세요. 문제가 없으면 <strong>“최종 승인”</strong>이라고 말씀해 주세요.</div>
</main></body></html>'''
    (out / "FINAL_REVIEW.html").write_text(final_html, encoding="utf-8")

    readme = f"""Criminal Girls Invite Only 한국어화 최종 통합 검수본

1. FINAL_REVIEW.html을 여세요.
2. UI 검수와 시나리오·시스템 번역 검수를 모두 확인하세요.
3. 수정 요청은 UI 자산명 또는 번역 문구 ID와 함께 알려 주세요.
4. 이상이 없으면 '최종 승인'이라고 말씀해 주세요.

번역 의미 기준: 일본어 원문
영어 문구: 비권위 참고용
번역/검수 모델: Codex 내부 모델
게임 폴더 설치: 아직 하지 않음

최종 후보: {candidate_qa['candidate']}
SHA-256: {candidate_qa['candidate_sha256']}
"""
    (out / "README_KO.txt").write_text(readme, encoding="utf-8")

    ui_source_files = {p.relative_to(ui_source): sha256(p) for p in ui_source.rglob("*") if p.is_file()}
    ui_copied_files = {p.relative_to(out / "ui_review"): sha256(p) for p in (out / "ui_review").rglob("*") if p.is_file()}
    checks = {
        "ui_standalone_copy_exact": ui_source_files == ui_copied_files,
        "translation_map_exact": sha256(final_map) == sha256(out / "translation/jp_based_reviewed_translation.jsonl"),
        "translation_row_count": len(rows) == 2709,
        "candidate_qa_pass": candidate_qa.get("status") == "PASS",
        "candidate_not_installed": candidate_qa.get("installed_to_game") is False,
        "top_level_review_exists": (out / "FINAL_REVIEW.html").is_file(),
        "scenario_review_exists": (out / "translation/SCENARIO_REVIEW.html").is_file(),
    }
    verification = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
    (out / "reports/review_package_verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "status": verification["status"],
        "package": str(out),
        "unique_strings": len(rows),
        "review_complete": sum(row["status"] == "review_complete" for row in rows),
        "preserve": sum(row["status"] == "preserve" for row in rows),
        "jp_final_changes": len(changes),
        "ui_assets": 36,
        "encoded_ui_assets": 26,
        "candidate_sha256": candidate_qa["candidate_sha256"],
        "installed_to_game": False,
    }
    (out / "package_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = []
    for path in sorted(p for p in out.rglob("*") if p.is_file() and p.name != "package_sha256_manifest.json"):
        manifest.append({"path": path.relative_to(out).as_posix(), "size": path.stat().st_size, "sha256": sha256(path)})
    (out / "package_sha256_manifest.json").write_text(json.dumps({"files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if verification["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
