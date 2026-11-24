#!/usr/bin/env python3
"""Freeze the Korean text map after a Japanese-original integrated review."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


REVIEWER = "Codex internal model"
REVIEW_PASS = "jp_original_integrated_review"

# Every entry is guarded by the exact Japanese source so an ID drift cannot
# silently apply a correction to the wrong string.
CORRECTIONS: dict[str, tuple[str, str]] = {
    "src_0651": ("地獄踏破はダテじゃないよ", "지옥을 돌파한 실력이 어디 가겠어!"),
    "src_0711": ("ぬるぬる調教", "미끈미끈 조교"),
    "src_0714": ("癒しモミモミ", "치유 주물주물"),
    "src_0723": ("毛箒でくすぐるおしおき。", "털 먼지털이로 간지럽히는 벌주기."),
    "src_0779": ("古き記憶の園", "옛 기억의 정원"),
    "src_0794": ("へ\n移動しますか？", " 방향으로\n이동하시겠습니까?"),
    "src_0896": ("『古き記憶の園』にあるのね。\nそこに行きましょう。", "『옛 기억의 정원』에 있구나.\n그곳으로 가자."),
    "src_0900": ("『古き記憶の園』にね。\n行きましょう。", "『옛 기억의 정원』으로.\n가자."),
    "src_0930": ("『古き記憶の園』に戻りましょう。", "『옛 기억의 정원』으로 돌아가자."),
    "src_0931": ("『古き記憶の園』にね。\n戻りましょう。", "『옛 기억의 정원』으로.\n돌아가자."),
    "src_1272": ("ラッキーかもん！", "행운이여, 와라!"),
    "src_1280": ("てんはのかた！", "천파의 자세!"),
    "src_1305": ("すすめ、よんじゅうし！", "나아가라, 사총사!"),
    "src_1442": ("攻撃を緩めるわ", "공격을 약하게 할게"),
    "src_1541": ("ぬるぬる調教を行う道具", "미끈미끈 조교에 사용하는 도구"),
    "src_1543": ("癒しモミモミを行う道具", "치유 주물주물에 사용하는 도구"),
    "src_1633": ("羽ぼうき", "깃털 먼지털이"),
    "src_2043": ("ぬるぬる調教改々", "미끈미끈 조교 개량²"),
    "src_2184": ("フィフスラッシュ", "피프스 슬래시"),
    "src_2306": ("ぬるぬる調教・改々", "미끈미끈 조교·개량²"),
    "src_2685": ("毛ぼうきでくすぐるおしおき。", "털 먼지털이로 간질이는 벌주기."),
    "src_2691": ("ぬるぬる調教のおしおき", "미끈미끈 조교 벌주기"),
    "src_2694": ("敵を羽ぼうきでこすって倒せ！", "깃털 먼지털이로 적을 간질여라!"),
}

PRESERVE_PLACEHOLDERS: dict[str, str] = {
    "src_0720": "バッファ",
    "src_1058": "予備",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--changes", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    rows = read_jsonl(args.input)
    if len(rows) != 2709:
        raise ValueError(f"expected 2709 unique source strings, got {len(rows)}")
    by_id = {row["source_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate source_id in input")

    changes: list[dict] = []
    for source_id, (expected_ja, new_ko) in CORRECTIONS.items():
        row = by_id[source_id]
        if row["source_ja"] != expected_ja:
            raise ValueError(f"source guard failed for {source_id}: {row['source_ja']!r}")
        old = row.get("reviewed_ko")
        row["reviewed_ko"] = new_ko
        row["status"] = "review_complete"
        row["reason"] = "translate"
        changes.append({
            "source_id": source_id,
            "source_ja": expected_ja,
            "before_ko": old,
            "after_ko": new_ko,
            "kind": "jp_fidelity_or_term_correction",
        })

    for source_id, expected_ja in PRESERVE_PLACEHOLDERS.items():
        row = by_id[source_id]
        if row["source_ja"] != expected_ja:
            raise ValueError(f"source guard failed for {source_id}: {row['source_ja']!r}")
        old = row.get("reviewed_ko")
        row["draft_ko"] = None
        row["reviewed_ko"] = None
        row["status"] = "preserve"
        row["reason"] = "development_placeholder"
        changes.append({
            "source_id": source_id,
            "source_ja": expected_ja,
            "before_ko": old,
            "after_ko": None,
            "kind": "preserve_development_placeholder",
        })

    for row in rows:
        row["semantic_source_language"] = "ja-JP"
        row["reference_en_role"] = "non_authoritative_reference_only"
        row["jp_basis_verified"] = True
        row["review_source"] = REVIEWER
        row["review_pass"] = REVIEW_PASS

    counts = Counter(row.get("status") for row in rows)
    if counts != Counter({"review_complete": 2637, "preserve": 72}):
        raise ValueError(f"unexpected status counts: {counts}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    args.changes.parent.mkdir(parents=True, exist_ok=True)
    with args.changes.open("w", encoding="utf-8", newline="\n") as f:
        for change in changes:
            f.write(json.dumps(change, ensure_ascii=False, separators=(",", ":")) + "\n")

    summary = {
        "status": "PASS",
        "semantic_source_language": "Japanese (ja-JP)",
        "english_reference_role": "non-authoritative reference only",
        "draft_model": REVIEWER,
        "integrated_review_model": REVIEWER,
        "total_unique_strings": len(rows),
        "review_complete": counts["review_complete"],
        "preserve": counts["preserve"],
        "corrections_applied": len(CORRECTIONS),
        "development_placeholders_restored": len(PRESERVE_PLACEHOLDERS),
        "input_sha256": sha256(args.input),
        "output_sha256": sha256(args.output),
        "changes_sha256": sha256(args.changes),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
