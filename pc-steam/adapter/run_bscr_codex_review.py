#!/usr/bin/env python3
"""Run the single integrated Codex-internal review over all BSCR draft packets.

The model is invoked only through the locally bundled Codex executable.  Every
packet result is validated before it is accepted.  Invalid rows are written to
``invalid/`` and can be repaired with ``--repair`` without rerunning good rows.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PROJECT = Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
V2 = PROJECT / "translation" / "bscr_v2"
PACKETS = V2 / "packets"
DRAFTS = V2 / "draft_results"
RESULTS = V2 / "reviewed_results"
INVALID = V2 / "review_invalid_results"
LOGS = V2 / "review_logs"
CODEX = PROJECT / "tools" / "codex-internal-windows.exe"

JP_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
TOKEN_RE = re.compile(
    r"\$[0-9]+"
    r"|%(?:[-+ #0]*[0-9]*(?:\.[0-9]+)?[A-Za-z%])"
    r"|\\[A-Za-z][A-Za-z0-9_]*"
    r"|\{[^{}\r\n]+\}"
    r"|<[^<>\r\n]+>"
)
NUMBER_RE = re.compile(r"(?<!\$)(?:[0-9０-９]+(?:[.,．，][0-9０-９]+)?)")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(encoded)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def token_counter(text: str):
    return collections.Counter(TOKEN_RE.findall(text))


def normalize_number(value: str) -> str:
    return value.translate(str.maketrans("０１２３４５６７８９．，", "0123456789.,"))


def number_counter(text: str):
    stripped = TOKEN_RE.sub("", text)
    return collections.Counter(normalize_number(x) for x in NUMBER_RE.findall(stripped))


def validate_row(source: dict, row: dict, require_translated: bool = True) -> list[dict]:
    issues: list[dict] = []
    cluster_id = source["cluster_id"]
    if row.get("cluster_id") != cluster_id:
        issues.append({"code": "cluster_id_mismatch", "actual": row.get("cluster_id")})
    for field in ("source_ja", "reference_en"):
        if field in row and row[field] != source.get(field):
            issues.append({"code": "immutable_field_mismatch", "field": field})
    status = row.get("status")
    target = row.get("target_ko", "")
    if status not in {"translated", "pending", "preserve"}:
        issues.append({"code": "invalid_status", "actual": status})
        return issues
    if require_translated and status != "translated":
        issues.append({"code": "final_status_not_translated", "actual": status})
        return issues
    if not isinstance(target, str):
        issues.append({"code": "target_not_string"})
        return issues
    if status == "translated":
        if not target:
            issues.append({"code": "empty_translation"})
            return issues
        if "\0" in target:
            issues.append({"code": "nul_in_translation"})
        if token_counter(target) != token_counter(source["source_ja"]):
            issues.append({"code": "protected_token_mismatch"})
        expected_nl = source["newline_signature"]
        actual_nl = {"lf": target.count("\n"), "cr": target.count("\r")}
        if actual_nl != expected_nl:
            issues.append({"code": "newline_mismatch", "expected": expected_nl, "actual": actual_nl})
        actual_bytes = len(target.encode("utf-8"))
        if actual_bytes > int(source["max_utf8_bytes"]):
            issues.append({"code": "utf8_byte_cap_exceeded", "cap": source["max_utf8_bytes"], "actual": actual_bytes})
        if JP_RE.search(target):
            issues.append({"code": "japanese_residue"})
        source_numbers = number_counter(source["source_ja"])
        target_numbers = number_counter(target)
        if source_numbers != target_numbers:
            row.setdefault("qa_warnings", []).append(
                {"code": "number_mismatch", "expected": dict(source_numbers), "actual": dict(target_numbers)}
            )
    elif target:
        issues.append({"code": f"{status}_has_target"})
    if status == "preserve":
        evidence = row.get("preserve_evidence")
        if not isinstance(evidence, dict) or not all(evidence.get(k) for k in ("kind", "artifact", "detail")):
            issues.append({"code": "unproven_preserve"})
    return issues


def validate_result(packet: dict, result, require_translated: bool = True) -> tuple[list[dict], list[dict]]:
    if isinstance(result, dict) and isinstance(result.get("rows"), list):
        rows = result["rows"]
    elif isinstance(result, list):
        rows = result
    else:
        return [], [{"code": "result_not_array_or_rows_object"}]
    sources = packet["entries"]
    source_by_id = {x["cluster_id"]: x for x in sources}
    by_id: dict[str, dict] = {}
    issues: list[dict] = []
    returned_ids: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append({"code": "row_not_object", "index": index})
            continue
        cid = row.get("cluster_id")
        if not isinstance(cid, str):
            issues.append({"code": "missing_cluster_id", "index": index})
            continue
        returned_ids.append(cid)
        if cid not in source_by_id:
            issues.append({"code": "unexpected_cluster_id", "cluster_id": cid})
            continue
        if cid in by_id:
            issues.append({"code": "duplicate_cluster_id", "cluster_id": cid})
            continue
        by_id[cid] = row
    expected = [x["cluster_id"] for x in sources]
    if returned_ids != expected:
        issues.append({"code": "order_or_set_mismatch"})
    accepted: list[dict] = []
    for source in sources:
        cid = source["cluster_id"]
        row = by_id.get(cid)
        if row is None:
            issues.append({"code": "missing_row", "cluster_id": cid})
            continue
        normalized = dict(row)
        normalized["source_ja"] = source["source_ja"]
        normalized["reference_en"] = source.get("reference_en", "")
        row_issues = validate_row(source, normalized, require_translated=require_translated)
        if row_issues:
            issues.extend({"cluster_id": cid, **item} for item in row_issues)
        else:
            clean = {
                "cluster_id": cid, "source_ja": source["source_ja"],
                "reference_en": source.get("reference_en", ""),
                "status": normalized["status"], "target_ko": normalized.get("target_ko", ""),
            }
            if normalized.get("qa_warnings"):
                clean["qa_warnings"] = normalized["qa_warnings"]
            if normalized["status"] == "preserve":
                clean["preserve_evidence"] = normalized["preserve_evidence"]
            accepted.append(clean)
    return accepted, issues


def output_schema(path: Path) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["rows"],
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["cluster_id", "source_ja", "reference_en", "status", "target_ko"],
                    "properties": {
                        "cluster_id": {"type": "string"},
                        "source_ja": {"type": "string"},
                        "reference_en": {"type": "string"},
                        "status": {"type": "string", "enum": ["translated", "pending", "preserve"]},
                        "target_ko": {"type": "string"},
                        "preserve_evidence": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["kind", "artifact", "detail"],
                            "properties": {
                                "kind": {"type": "string"},
                                "artifact": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                        },
                    },
                },
            }
        },
    }
    atomic_json(path, schema)


def make_review_prompt(packet: dict, draft: dict, repair_issues: list[dict] | None = None) -> str:
    draft_rows = draft.get("rows", draft if isinstance(draft, list) else [])
    draft_by_id = {x["cluster_id"]: x for x in draft_rows}
    entries = packet["entries"]
    if repair_issues:
        bad = {x.get("cluster_id") for x in repair_issues if x.get("cluster_id")}
        entries = [x for x in entries if x["cluster_id"] in bad]
    compact_entries = []
    keep = (
        "cluster_id", "source_ja", "reference_en", "occurrence_count",
        "max_utf8_bytes", "protected_tokens", "newline_signature",
        "candidate_classes", "consumer_roles", "context_samples",
        "occurrence_review_required", "conflict_reasons",
    )
    for source in entries:
        row = {key: source[key] for key in keep if key in source}
        row["draft_ko"] = draft_by_id[source["cluster_id"]]["target_ko"]
        if "context_samples" in row:
            row["context_samples"] = [
                {key: sample[key] for key in ("file", "prev_ja", "next_ja", "candidate_class", "consumer_roles") if key in sample}
                for sample in row["context_samples"]
            ]
        compact_entries.append(row)
    style = (V2 / "style_guide_bscr.md").read_text(encoding="utf-8-sig")
    glossary = (V2 / "glossary_bscr.json").read_text(encoding="utf-8-sig")
    repair = ""
    if repair_issues:
        repair = "\nThis retry must resolve every listed validation failure:\n" + json.dumps(repair_issues, ensure_ascii=False, indent=2)
    return f"""Perform the one integrated Korean review pass for this complete BSCR packet.
Japanese source is authoritative; English is reference-only. Independently compare every draft against source and context.
Do not rubber-stamp the draft. Correct mistranslation, omission, awkward Korean, spacing, terminology, character voice,
particles, honorifics, ellipses, explicitness, and system-message style. Use the locked spelling '걸즈 오더'.
Every input cluster must be returned exactly once, in order, with status translated and a nonempty target_ko.
Preserve protected tokens and exact LF/CR counts. The UTF-8 byte cap is absolute; shorten naturally to fit.
Never use the Japanese prolonged sound mark U+30FC in Korean. Count actual UTF-8 bytes before returning each target.
Replace all Japanese kana in emoticons too; for example, replace the katakana hand glyph \u30ce with a Korean-safe ASCII symbol such as /.
Do not leave Japanese, invent meaning, add explanations, or return Markdown.

STYLE GUIDE:
{style}

GLOSSARY:
{glossary}
{repair}

PACKET WITH FIRST DRAFTS:
{json.dumps({"packet_id": packet["packet_id"], "entries": compact_entries}, ensure_ascii=False, indent=2)}
"""

def invoke(packet_path: Path, args, repair: bool = False) -> dict:
    packet = load_json(packet_path)
    result_path = RESULTS / packet_path.name
    invalid_path = INVALID / packet_path.name
    log_path = LOGS / (packet_path.stem + (".repair.log" if repair else ".log"))
    draft_path = DRAFTS / packet_path.name
    if not draft_path.exists():
        raise RuntimeError(f"missing first draft: {draft_path}")
    draft = load_json(draft_path)
    draft_accepted, draft_issues = validate_result(packet, draft, require_translated=False)
    if draft_issues or len(draft_accepted) != packet["entry_count"]:
        raise RuntimeError(f"first draft is not complete/valid: {packet_path.name} issues={len(draft_issues)}")
    prior_issues = None
    if repair:
        if not invalid_path.exists():
            return {"packet": packet_path.name, "status": "no_invalid_file"}
        recorded = load_json(invalid_path).get("issues", [])
        bad_ids = {x.get("cluster_id") for x in recorded if x.get("cluster_id")}
        if not bad_ids and result_path.exists():
            current = load_json(result_path)
            current_rows = current.get("rows", current if isinstance(current, list) else [])
            have_ids = {x.get("cluster_id") for x in current_rows if isinstance(x, dict)}
            bad_ids = {x["cluster_id"] for x in packet["entries"] if x["cluster_id"] not in have_ids}
        prior_issues = [{"code": "review_required", "cluster_id": cid} for cid in sorted(bad_ids)]
        if not prior_issues:
            return {"packet": packet_path.name, "status": "no_issues"}
    prompt = make_review_prompt(packet, draft, prior_issues)
    schema_path = V2 / "schema" / "codex_cluster_result.schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    if not schema_path.exists():
        output_schema(schema_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_output = result_path.with_suffix(".raw.tmp.json")
    cmd = [
        str(args.codex), "exec", "-", "-m", args.model,
        "-c", f'model_reasoning_effort="{args.reasoning}"',
        "-s", "read-only", "--skip-git-repo-check", "--ephemeral",
        "--output-schema", str(schema_path), "-o", str(tmp_output),
        "-C", str(PROJECT), "--color", "never",
    ]
    started = time.time()
    proc = subprocess.run(
        cmd,
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=args.timeout,
        check=False,
    )
    log_path.write_bytes(proc.stdout)
    if proc.returncode != 0 or not tmp_output.exists():
        atomic_json(invalid_path, {"packet": packet_path.name, "returncode": proc.returncode, "issues": [{"code": "codex_process_failed"}]})
        return {"packet": packet_path.name, "status": "process_failed", "returncode": proc.returncode, "seconds": round(time.time()-started, 1)}
    try:
        raw = load_json(tmp_output)
    except Exception as exc:
        atomic_json(invalid_path, {"packet": packet_path.name, "issues": [{"code": "invalid_json", "detail": str(exc)}]})
        tmp_output.unlink(missing_ok=True)
        return {"packet": packet_path.name, "status": "invalid_json", "seconds": round(time.time()-started, 1)}
    accepted, issues = validate_result(packet, raw)
    direct_row_issues = [
        issue for issue in issues
        if issue.get("code") not in {
            "order_or_set_mismatch", "missing_row", "unexpected_cluster_id", "duplicate_cluster_id"
        }
    ]
    if repair and result_path.exists():
        old = load_json(result_path)
        old_rows = old.get("rows", old if isinstance(old, list) else [])
        source_by_id = {x["cluster_id"]: x for x in packet["entries"]}
        good = {}
        for row in old_rows:
            cid = row.get("cluster_id") if isinstance(row, dict) else None
            source = source_by_id.get(cid)
            if source is None:
                continue
            normalized = dict(row)
            normalized["source_ja"] = source["source_ja"]
            normalized["reference_en"] = source.get("reference_en", "")
            if not validate_row(source, normalized):
                good[cid] = normalized
        good.update({x["cluster_id"]: x for x in accepted})
        merged = [good[x["cluster_id"]] for x in packet["entries"] if x["cluster_id"] in good]
        accepted, merged_issues = validate_result(packet, {"rows": merged})
        issues = direct_row_issues + merged_issues
    atomic_json(result_path, {"rows": accepted})
    tmp_output.unlink(missing_ok=True)
    if issues:
        atomic_json(invalid_path, {"packet": packet_path.name, "issues": issues, "accepted": len(accepted), "expected": packet["entry_count"]})
        status = "needs_repair"
    else:
        invalid_path.unlink(missing_ok=True)
        status = "ok"
    return {"packet": packet_path.name, "status": status, "accepted": len(accepted), "issues": len(issues), "seconds": round(time.time()-started, 1)}


def already_valid(packet_path: Path) -> bool:
    result_path = RESULTS / packet_path.name
    if not result_path.exists():
        return False
    try:
        accepted, issues = validate_result(load_json(packet_path), load_json(result_path))
        return not issues and len(accepted) == load_json(packet_path)["entry_count"]
    except Exception:
        return False


def build_summary(packet_paths: list[Path]) -> dict:
    status = collections.Counter()
    translated = pending = preserve = 0
    issues = 0
    for path in packet_paths:
        result = RESULTS / path.name
        invalid = INVALID / path.name
        if already_valid(path):
            status["valid"] += 1
            rows = load_json(result)["rows"]
            counts = collections.Counter(x["status"] for x in rows)
            translated += counts["translated"]
            pending += counts["pending"]
            preserve += counts["preserve"]
        elif result.exists():
            status["partial_or_invalid"] += 1
        else:
            status["missing"] += 1
        if invalid.exists():
            issues += len(load_json(invalid).get("issues", []))
    summary = {
        "packet_count": len(packet_paths), "packet_status": dict(status),
        "translated_clusters": translated, "pending_clusters": pending,
        "preserve_clusters": preserve, "validation_issue_count": issues,
    }
    atomic_json(V2 / "batch_status.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--codex", type=Path, default=CODEX)
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--reasoning", default="medium")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int)
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    paths = sorted(PACKETS.glob("packet_*.json"))
    if args.status:
        print(json.dumps(build_summary(paths), ensure_ascii=False, indent=2))
        return 0
    chosen = []
    for path in paths:
        number = int(path.stem.split("_")[-1])
        if number < args.start or (args.end is not None and number > args.end):
            continue
        if args.repair:
            if not (INVALID / path.name).exists():
                continue
        elif already_valid(path):
            continue
        chosen.append(path)
    if not args.codex.exists():
        raise SystemExit(f"missing bundled Codex executable: {args.codex}")
    print(f"running {len(chosen)} packets with {args.workers} worker(s)", flush=True)
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(invoke, p, args, args.repair): p for p in chosen}
        for future in concurrent.futures.as_completed(futures):
            try:
                info = future.result()
            except Exception as exc:
                info = {"packet": futures[future].name, "status": "exception", "detail": repr(exc)}
            print(json.dumps(info, ensure_ascii=False), flush=True)
            if info.get("status") != "ok":
                failures += 1
    summary = build_summary(paths)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
