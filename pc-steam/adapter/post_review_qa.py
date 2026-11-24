#!/usr/bin/env python3
import json, re, sys
from pathlib import Path

src=Path(sys.argv[1]); out=Path(sys.argv[2])
rows=[json.loads(x) for x in src.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
reviewed=[r for r in rows if r.get("status")=="review_complete"]
issues=[]
particle=re.compile(r"(?:은\(는\)|이\(가\)|을\(를\)|과\(와\)|와\(과\)|으\(로\))")
pairs=[("【","】"),("「","」"),("『","』"),("(",")")]
for r in reviewed:
    ja=r.get("source_ja",""); ko=r.get("reviewed_ko","")
    flags=[]
    if not ko: flags.append("empty")
    if "�" in ko: flags.append("replacement_char")
    if re.search(r"[ぁ-ゖァ-ヺ]",ko): flags.append("kana")
    if re.search(r"[一-龯々〆〤]",ko): flags.append("cjk")
    if particle.search(ko): flags.append("particle_placeholder")
    if ja.count("\n")!=ko.count("\n"): flags.append("newline_mismatch")
    if any(ko.count(a)!=ko.count(b) for a,b in pairs): flags.append("bracket_mismatch")
    if flags: issues.append({"source_id":r["source_id"],"flags":flags,"source_ja":ja,"reviewed_ko":ko})
summary={
    "total_unique":len(rows),
    "review_complete":len(reviewed),
    "preserve":sum(r.get("status")=="preserve" for r in rows),
    "empty":sum("empty" in x["flags"] for x in issues),
    "replacement_chars":sum("replacement_char" in x["flags"] for x in issues),
    "japanese_kana_remaining":sum("kana" in x["flags"] for x in issues),
    "cjk_remaining":sum("cjk" in x["flags"] for x in issues),
    "particle_placeholders":sum("particle_placeholder" in x["flags"] for x in issues),
    "newline_mismatches":sum("newline_mismatch" in x["flags"] for x in issues),
    "bracket_mismatches":sum("bracket_mismatch" in x["flags"] for x in issues),
    "issue_rows":len(issues),
    "passed":len(reviewed)==2637 and sum(r.get("status")=="preserve" for r in rows)==72 and not issues,
}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({"summary":summary,"issues":issues},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False,indent=2))
if not summary["passed"]: raise SystemExit(1)
