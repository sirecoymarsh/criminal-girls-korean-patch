#!/usr/bin/env python3
"""Strict structural and terminology QA for the Japanese-based frozen map."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


KANA_RE = re.compile(r"[ぁ-ゖァ-ヺ]")
CJK_RE = re.compile(r"[一-龯々〆〤]")
PARTICLE_RE = re.compile(r"(?:은\(는\)|이\(가\)|을\(를\)|과\(와\)|와\(과\)|으\(로\))")
PRINTF_RE = re.compile(r"%(?:\d+\$)?[-+#0 .'\d*]*[A-Za-z%]")
PAIRS = (("【", "】"), ("「", "」"), ("『", "』"), ("(", ")"))

TERM_RULES = {
    "おしおき": "벌주기",
    "更生": "갱생",
    "囚監フロア": "수감동",
    "泥ノ試練": "진흙의 시련",
    "炎ノ試練": "불꽃의 시련",
    "氷ノ試練": "얼음의 시련",
    "古き記憶の園": "옛 기억의 정원",
    "少女地獄": "소녀 지옥",
    "クリミナル": "크리미널",
    "キズナ": "유대",
    "ぬるぬる調教": "미끈미끈 조교",
    "癒しモミモミ": "치유 주물주물",
    "羽ぼうき": "깃털 먼지털이",
}

STALE_KOREAN = (
    "미끌미끌 조교",
    "오래된 기억의 정원",
    "먼지떨이",
    "피프스 러시",
    "나아가라, 사십사",
    "천하의 자세",
)

SOURCE_FIELDS = (
    "source_id", "source_ja", "reference_en", "reference_variants",
    "occurrence_count", "lanes", "contexts", "context_truncated",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def issue(issues: list[dict], row: dict, flag: str, detail: object = None) -> None:
    item = {"source_id": row.get("source_id"), "flag": flag}
    if detail is not None:
        item["detail"] = detail
    issues.append(item)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("final", type=Path)
    ap.add_argument("baseline", type=Path)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()

    rows = read_jsonl(args.final)
    baseline = read_jsonl(args.baseline)
    catalog = read_jsonl(args.catalog)
    issues: list[dict] = []

    if len(rows) != 2709:
        issues.append({"flag": "unique_count", "detail": len(rows)})
    ids = [row.get("source_id") for row in rows]
    if len(set(ids)) != len(ids):
        issues.append({"flag": "duplicate_source_id"})
    if ids != [row.get("source_id") for row in baseline]:
        issues.append({"flag": "source_id_order_changed"})

    baseline_by_id = {row["source_id"]: row for row in baseline}
    for row in rows:
        old = baseline_by_id.get(row.get("source_id"))
        if not old:
            issue(issues, row, "unknown_source_id")
            continue
        mutated = [field for field in SOURCE_FIELDS if row.get(field) != old.get(field)]
        if mutated:
            issue(issues, row, "source_provenance_mutated", mutated)

        status = row.get("status")
        ko = row.get("reviewed_ko")
        ja = row.get("source_ja", "")
        if row.get("semantic_source_language") != "ja-JP" or not row.get("jp_basis_verified"):
            issue(issues, row, "jp_basis_metadata_missing")
        if row.get("review_source") != "Codex internal model":
            issue(issues, row, "review_model_mismatch")
        if row.get("review_pass") != "jp_original_integrated_review":
            issue(issues, row, "review_pass_mismatch")

        if status == "review_complete":
            if not isinstance(ko, str) or not ko:
                issue(issues, row, "empty_translation")
                continue
            if "�" in ko:
                issue(issues, row, "replacement_character")
            if KANA_RE.search(ko):
                issue(issues, row, "japanese_kana_remaining")
            if CJK_RE.search(ko):
                issue(issues, row, "cjk_remaining")
            if PARTICLE_RE.search(ko):
                issue(issues, row, "particle_placeholder")
            if ja.count("\n") != ko.count("\n"):
                issue(issues, row, "newline_count_mismatch", [ja.count("\n"), ko.count("\n")])
            for left, right in PAIRS:
                if ko.count(left) != ko.count(right):
                    issue(issues, row, "bracket_mismatch", left + right)
            if Counter(PRINTF_RE.findall(ja)) != Counter(PRINTF_RE.findall(ko)):
                issue(issues, row, "printf_token_mismatch", [PRINTF_RE.findall(ja), PRINTF_RE.findall(ko)])
            for ja_term, ko_term in TERM_RULES.items():
                if ja_term in ja and ko_term not in ko:
                    issue(issues, row, "term_mismatch", {"ja": ja_term, "expected_ko": ko_term})
            stale = [term for term in STALE_KOREAN if term in ko]
            if stale:
                issue(issues, row, "stale_korean_term", stale)
        elif status == "preserve":
            if ko is not None:
                issue(issues, row, "preserve_has_translation", ko)
        else:
            issue(issues, row, "invalid_status", status)

    counts = Counter(row.get("status") for row in rows)
    if counts != Counter({"review_complete": 2637, "preserve": 72}):
        issues.append({"flag": "status_counts", "detail": dict(counts)})

    catalog_sources = Counter(row.get("source_ja") for row in catalog)
    missing_catalog_sources = [row["source_id"] for row in rows if row["source_ja"] not in catalog_sources]
    if missing_catalog_sources:
        issues.append({"flag": "sources_missing_from_catalog", "detail": missing_catalog_sources})

    by_id = {row["source_id"]: row for row in rows}
    for source_id, source_ja in (("src_0720", "バッファ"), ("src_1058", "予備")):
        row = by_id[source_id]
        if row.get("status") != "preserve" or row.get("source_ja") != source_ja:
            issue(issues, row, "development_placeholder_not_preserved")

    flag_counts = Counter(item["flag"] for item in issues)
    report = {
        "status": "PASS" if not issues else "FAIL",
        "semantic_source_language": "Japanese (ja-JP)",
        "review_model": "Codex internal model",
        "integrated_review": True,
        "total_unique_strings": len(rows),
        "review_complete": counts.get("review_complete", 0),
        "preserve": counts.get("preserve", 0),
        "catalog_occurrences": len(catalog),
        "issue_count": len(issues),
        "issue_counts": dict(sorted(flag_counts.items())),
        "final_sha256": sha256(args.final),
        "baseline_sha256": sha256(args.baseline),
        "catalog_sha256": sha256(args.catalog),
        "issues": issues,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "issues"}, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
