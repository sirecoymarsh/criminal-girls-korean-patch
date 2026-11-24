#!/usr/bin/env python3
"""Resolve the 59 context-sensitive BSCR occurrences with the bundled Codex model."""

from __future__ import annotations
import argparse, collections, json, os, re, subprocess, tempfile, time
from pathlib import Path

PROJECT=Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
V2=PROJECT/"translation/bscr_v2"
INPUT=V2/"occurrence_review_packets.json"
OUTPUT=V2/"occurrence_overrides.json"
WORK=V2/"occurrence_override_work"
CODEX=PROJECT/"tools/codex-internal-windows.exe"
JP_RE=re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
TOKEN_RE=re.compile(r"\$[0-9]+|%(?:[-+ #0]*[0-9]*(?:\.[0-9]+)?[A-Za-z%])|\\[A-Za-z][A-Za-z0-9_]*|\{[^{}\r\n]+\}|<[^<>\r\n]+>")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
            json.dump(data,f,ensure_ascii=False,separators=(",",":"))
            f.write("\n")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def flatten():
    doc=read(INPUT)
    rows=[]
    for cluster in doc["clusters"]:
        for occ in cluster["occurrences"]:
            row=dict(occ)
            row["translation_cluster_id"]=cluster["cluster_id"]
            row["conflict_reasons"]=cluster.get("conflict_reasons",[])
            rows.append(row)
    assert len(rows)==doc["occurrence_count"]==59
    assert len({x["uid"] for x in rows})==59
    return rows


def schema(path):
    doc={
      "$schema":"https://json-schema.org/draft/2020-12/schema",
      "type":"object","additionalProperties":False,"required":["rows"],
      "properties":{"rows":{"type":"array","items":{
        "type":"object","additionalProperties":False,
        "required":["uid","status","target_ko"],
        "properties":{
          "uid":{"type":"string","pattern":"^bscr2:"},
          "status":{"type":"string","enum":["translated"]},
          "target_ko":{"type":"string","minLength":1}
        }}}}
    }
    atomic(path,doc)


def counter(pattern,text):
    return collections.Counter(pattern.findall(text))


def validate_one(source,row):
    issues=[]
    if not isinstance(row,dict):
        return ["row_not_object"]
    if row.get("uid")!=source["uid"]: issues.append("uid_mismatch")
    if row.get("status")!="translated": issues.append("not_translated")
    target=row.get("target_ko")
    if not isinstance(target,str) or not target: return issues+["empty_target"]
    if "\0" in target: issues.append("nul")
    if JP_RE.search(target): issues.append("japanese_residue")
    if len(target.encode("utf-8"))>int(source["max_utf8_bytes"]): issues.append("byte_cap")
    sig=source["newline_signature"]
    if target.count("\n")!=int(sig["lf"]) or target.count("\r")!=int(sig["cr"]): issues.append("newline")
    if counter(TOKEN_RE,target)!=counter(TOKEN_RE,source["source_ja"]): issues.append("protected_tokens")
    return issues


def compact(row):
    return {k:row.get(k) for k in (
      "uid","translation_cluster_id","file","segment_index","relative_offset",
      "source_ja","reference_en","prev_ja","next_ja","candidate_class",
      "consumer_roles","consumer_opcodes","max_utf8_bytes","protected_tokens",
      "newline_signature","conflict_reasons"
    )}


def prompt(rows,failures):
    style=(V2/"style_guide_bscr.md").read_text(encoding="utf-8-sig")
    glossary=(V2/"glossary_bscr.json").read_text(encoding="utf-8-sig")
    repair=""
    if failures:
        repair="\nPrevious validation failures by UID:\n"+json.dumps(failures,ensure_ascii=False,indent=2)
    return f"""You are the sole final Korean localization reviewer for these context-sensitive BSCR occurrences.
Translate from Japanese. English is only a supplemental reference and may be untranslated or wrong.
Return every requested UID exactly once and in the input order. Every row must have status translated.
Use natural Korean suited to the neighboring lines and consumer role. Preserve protected tokens and exact LF/CR counts.
The UTF-8 byte cap is absolute. Shorten naturally until each target fits. Do not leave Japanese or output explanations.
Repeated Japanese may require different Korean only when its occurrence context proves a different meaning.

STYLE GUIDE:
{style}

GLOSSARY:
{glossary}
{repair}

INPUT OCCURRENCES:
{json.dumps([compact(x) for x in rows],ensure_ascii=False,indent=2)}
"""


def invoke(rows,args,pass_no,failures):
    WORK.mkdir(parents=True,exist_ok=True)
    schema_path=WORK/"result.schema.json"
    schema(schema_path)
    raw=WORK/f"pass_{pass_no:02d}.raw.json"
    log=WORK/f"pass_{pass_no:02d}.log"
    cmd=[str(args.codex),"exec","-","-m",args.model,"-c",f'model_reasoning_effort="{args.reasoning}"',
         "-s","read-only","--skip-git-repo-check","--ephemeral","--output-schema",str(schema_path),
         "-o",str(raw),"-C",str(PROJECT),"--color","never"]
    started=time.time()
    proc=subprocess.run(cmd,input=prompt(rows,failures).encode("utf-8"),stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,timeout=args.timeout,check=False)
    log.write_bytes(proc.stdout)
    if proc.returncode or not raw.exists():
        raise RuntimeError(f"Codex occurrence pass failed: pass={pass_no} returncode={proc.returncode}")
    doc=read(raw)
    values=doc.get("rows") if isinstance(doc,dict) else None
    if not isinstance(values,list):
        raise RuntimeError("Codex result has no rows array")
    print(json.dumps({"pass":pass_no,"requested":len(rows),"returned":len(values),
                      "seconds":round(time.time()-started,1)},ensure_ascii=False),flush=True)
    return values


def final_row(source,target):
    keys=("uid","translation_cluster_id","file","segment_index","relative_offset",
          "source_ja","source_sha256","source_utf8_bytes","original_file_sha256")
    out={k:source[k] for k in keys}
    out.update({"status":"translated","target_ko":target["target_ko"],
                "provenance":{"translator":"Codex internal model","model":"gpt-5.5",
                              "review_lane":"occurrence_context_override"}})
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--codex",type=Path,default=CODEX)
    ap.add_argument("--model",default="gpt-5.5")
    ap.add_argument("--reasoning",default="medium")
    ap.add_argument("--timeout",type=int,default=1800)
    ap.add_argument("--max-passes",type=int,default=5)
    ap.add_argument("--force",action="store_true")
    args=ap.parse_args()
    sources=flatten(); by_uid={x["uid"]:x for x in sources}
    accepted={}
    if OUTPUT.exists() and not args.force:
        prior=read(OUTPUT)
        if isinstance(prior,list):
            for row in prior:
                uid=row.get("uid") if isinstance(row,dict) else None
                if uid in by_uid and not validate_one(by_uid[uid],row):
                    accepted[uid]={"uid":uid,"status":"translated","target_ko":row["target_ko"]}
    failures={}
    for pass_no in range(1,args.max_passes+1):
        wanted=[x for x in sources if x["uid"] not in accepted]
        if not wanted: break
        values=invoke(wanted,args,pass_no,failures)
        returned={x.get("uid"):x for x in values if isinstance(x,dict) and isinstance(x.get("uid"),str)}
        failures={}
        for source in wanted:
            row=returned.get(source["uid"])
            issues=validate_one(source,row)
            if issues: failures[source["uid"]]=issues
            else: accepted[source["uid"]]=row
        atomic(WORK/f"pass_{pass_no:02d}.validation.json",
               {"requested":len(wanted),"accepted_total":len(accepted),"failures":failures})
    missing=[x["uid"] for x in sources if x["uid"] not in accepted]
    if missing:
        atomic(WORK/"unresolved.json",{"missing":missing,"count":len(missing),"failures":failures})
        raise SystemExit(f"unresolved occurrence overrides: {len(missing)}")
    final=[final_row(x,accepted[x["uid"]]) for x in sources]
    atomic(OUTPUT,final)
    print(json.dumps({"status":"PASS","rows":len(final),"output":str(OUTPUT)},ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
