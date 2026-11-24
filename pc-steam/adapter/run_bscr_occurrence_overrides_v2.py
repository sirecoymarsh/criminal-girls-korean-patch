#!/usr/bin/env python3
"""Draft, then independently review, the 59 context-sensitive BSCR occurrences."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import run_bscr_occurrence_overrides as base

PROJECT = base.PROJECT
V2 = base.V2
CODEX = base.CODEX


def load_draft(path: Path, sources: list[dict]) -> dict[str, dict]:
    rows = base.read(path)
    if not isinstance(rows, list):
        raise ValueError("draft override file must be an array")
    by_source = {row["uid"]: row for row in sources}
    result: dict[str, dict] = {}
    for row in rows:
        uid = row.get("uid") if isinstance(row, dict) else None
        if uid not in by_source:
            raise ValueError(f"unknown draft UID: {uid}")
        issues = base.validate_one(by_source[uid], row)
        if issues:
            raise ValueError(f"invalid draft override {uid}: {issues}")
        result[uid] = row
    if set(result) != set(by_source):
        raise ValueError(f"draft override coverage mismatch: {len(result)} != {len(by_source)}")
    return result


def prompt(rows: list[dict], failures: dict, mode: str, drafts: dict[str, dict] | None) -> str:
    style = (V2 / "style_guide_bscr.md").read_text(encoding="utf-8-sig")
    glossary = (V2 / "glossary_bscr.json").read_text(encoding="utf-8-sig")
    repair = ""
    if failures:
        repair = "\nPrevious validation failures by UID:\n" + json.dumps(failures, ensure_ascii=False, indent=2)
    payload = []
    for row in rows:
        item = base.compact(row)
        if drafts is not None:
            item["draft_ko"] = drafts[row["uid"]]["target_ko"]
        payload.append(item)
    if mode == "draft":
        role = """You are the first-pass Korean translator for these context-sensitive BSCR occurrences.
Translate each Japanese occurrence into a natural Korean draft. English is only supplemental.
This is a draft pass, but every structural constraint is mandatory."""
    else:
        role = """You are the independent integrated Korean reviewer for these context-sensitive BSCR occurrences.
Review Japanese, context, English reference, and draft_ko. Rewrite weak or inaccurate drafts instead of merely copying them.
The Japanese source is authoritative. Return polished final Korean with consistent voice and terminology."""
    return f"""{role}
Return every requested UID exactly once and in input order. Every row must have status translated.
Preserve protected tokens and exact LF/CR counts. The UTF-8 byte cap is absolute.
Shorten naturally until each target fits. Do not leave Japanese and do not output explanations.
Repeated Japanese may require different Korean when occurrence context proves a different meaning.

STYLE GUIDE:
{style}

GLOSSARY:
{glossary}
{repair}

INPUT OCCURRENCES:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def invoke(
    rows: list[dict],
    args,
    pass_no: int,
    failures: dict,
    drafts: dict[str, dict] | None,
    work: Path,
) -> list[dict]:
    work.mkdir(parents=True, exist_ok=True)
    schema_path = work / "result.schema.json"
    base.schema(schema_path)
    raw = work / f"pass_{pass_no:02d}.raw.json"
    log = work / f"pass_{pass_no:02d}.log"
    command = [
        str(args.codex), "exec", "-", "-m", args.model,
        "-c", f'model_reasoning_effort="{args.reasoning}"',
        "-s", "read-only", "--skip-git-repo-check", "--ephemeral",
        "--output-schema", str(schema_path), "-o", str(raw),
        "-C", str(PROJECT), "--color", "never",
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        input=prompt(rows, failures, args.mode, drafts).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=args.timeout,
        check=False,
    )
    log.write_bytes(completed.stdout)
    if completed.returncode or not raw.exists():
        raise RuntimeError(f"Codex occurrence {args.mode} pass failed: {pass_no} rc={completed.returncode}")
    doc = base.read(raw)
    values = doc.get("rows") if isinstance(doc, dict) else None
    if not isinstance(values, list):
        raise RuntimeError("Codex result has no rows array")
    print(json.dumps({
        "mode": args.mode,
        "pass": pass_no,
        "requested": len(rows),
        "returned": len(values),
        "seconds": round(time.time() - started, 1),
    }, ensure_ascii=False), flush=True)
    return values


def final_row(source: dict, target: dict, mode: str, model: str) -> dict:
    keys = (
        "uid", "translation_cluster_id", "file", "segment_index", "relative_offset",
        "source_ja", "source_sha256", "source_utf8_bytes", "original_file_sha256",
    )
    out = {key: source[key] for key in keys}
    out.update({
        "status": "translated",
        "target_ko": target["target_ko"],
        "provenance": {
            "translator": "Codex internal model",
            "model": model,
            "phase": "first_draft" if mode == "draft" else "integrated_review",
            "review_lane": "occurrence_context_override",
        },
    })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("draft", "review"), required=True)
    ap.add_argument("--draft", type=Path, default=V2 / "occurrence_overrides_draft.json")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--work", type=Path)
    ap.add_argument("--codex", type=Path, default=CODEX)
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--reasoning")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--max-passes", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.reasoning is None:
        args.reasoning = "low" if args.mode == "draft" else "medium"
    if args.output is None:
        args.output = args.draft if args.mode == "draft" else V2 / "occurrence_overrides.json"
    if args.work is None:
        args.work = V2 / ("occurrence_override_draft_work" if args.mode == "draft" else "occurrence_override_review_work")

    sources = base.flatten()
    by_uid = {row["uid"]: row for row in sources}
    drafts = load_draft(args.draft, sources) if args.mode == "review" else None
    accepted: dict[str, dict] = {}
    if args.output.exists() and not args.force:
        prior = base.read(args.output)
        if isinstance(prior, list):
            for row in prior:
                uid = row.get("uid") if isinstance(row, dict) else None
                if uid in by_uid and not base.validate_one(by_uid[uid], row):
                    accepted[uid] = {"uid": uid, "status": "translated", "target_ko": row["target_ko"]}

    failures: dict = {}
    for pass_no in range(1, args.max_passes + 1):
        wanted = [row for row in sources if row["uid"] not in accepted]
        if not wanted:
            break
        values = invoke(wanted, args, pass_no, failures, drafts, args.work)
        returned = {
            row.get("uid"): row
            for row in values
            if isinstance(row, dict) and isinstance(row.get("uid"), str)
        }
        failures = {}
        for source in wanted:
            row = returned.get(source["uid"])
            issues = base.validate_one(source, row)
            if issues:
                failures[source["uid"]] = issues
            else:
                accepted[source["uid"]] = row
        base.atomic(args.work / f"pass_{pass_no:02d}.validation.json", {
            "mode": args.mode,
            "requested": len(wanted),
            "accepted_total": len(accepted),
            "failures": failures,
        })

    missing = [row["uid"] for row in sources if row["uid"] not in accepted]
    if missing:
        base.atomic(args.work / "unresolved.json", {
            "mode": args.mode,
            "missing": missing,
            "count": len(missing),
            "failures": failures,
        })
        raise SystemExit(f"unresolved occurrence {args.mode} rows: {len(missing)}")

    final = [final_row(source, accepted[source["uid"]], args.mode, args.model) for source in sources]
    base.atomic(args.output, final)
    print(json.dumps({
        "status": "PASS",
        "mode": args.mode,
        "rows": len(final),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
