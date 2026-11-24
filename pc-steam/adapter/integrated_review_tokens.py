#!/usr/bin/env python3
import json, re, sys, unicodedata
from pathlib import Path

src = Path(sys.argv[1])
out = Path(sys.argv[2])
rows = [json.loads(x) for x in src.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
rows = [r for r in rows if r.get("status") == "draft_complete"]
STAT_RE = re.compile(r"(?<![A-Za-z0-9])(?:HP|MP|OP|ATK|DEF|MAT|MDF|SPD|EXP|EXTRA|EX|BGM|SE|VOICE)(?![A-Za-z0-9])", re.I)
NUM_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?")
CODE_RE = re.compile(r"\b(?:KN18[A-I]|XG06|UL77)\b", re.I)
issues = []
for r in rows:
    ja = unicodedata.normalize("NFKC", r.get("source_ja", ""))
    ko = unicodedata.normalize("NFKC", r.get("draft_ko", ""))
    src_stats = sorted(x.upper() for x in STAT_RE.findall(ja))
    ko_stats = sorted(x.upper() for x in STAT_RE.findall(ko))
    src_nums = sorted(NUM_RE.findall(ja))
    ko_nums = sorted(NUM_RE.findall(ko))
    src_codes = sorted(x.upper() for x in CODE_RE.findall(ja))
    ko_codes = sorted(x.upper() for x in CODE_RE.findall(ko))
    why = []
    if src_stats != ko_stats: why.append({"stats": [src_stats, ko_stats]})
    if src_nums != ko_nums: why.append({"numbers": [src_nums, ko_nums]})
    if src_codes != ko_codes: why.append({"codes": [src_codes, ko_codes]})
    if why:
        issues.append({"source_id":r["source_id"],"source_ja":r.get("source_ja",""),"draft_ko":r.get("draft_ko",""),"why":why})
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in issues),encoding="utf-8")
print(json.dumps({"review_scope":len(rows),"token_mismatch_candidates":len(issues)},ensure_ascii=False,indent=2))
