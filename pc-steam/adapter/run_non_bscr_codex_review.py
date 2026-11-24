#!/usr/bin/env python3
"""Run the single integrated Codex-internal review for all non-BSCR translations."""
from __future__ import annotations
import argparse, collections, hashlib, json, os, re, subprocess, tempfile, time, unicodedata
from pathlib import Path

PROJECT=Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
SOURCE=PROJECT/"translation/jp_based_reviewed_translation.jsonl"
OUTROOT=PROJECT/"translation/non_bscr_integrated_review_v2"
PACKETS=OUTROOT/"packets"; RESULTS=OUTROOT/"results"; INVALID=OUTROOT/"invalid"; LOGS=OUTROOT/"logs"
FINAL=PROJECT/"translation/jp_based_final_review_v2.jsonl"
CODEX=PROJECT/"tools/codex-internal-windows.exe"
JP_RE=re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
TOKEN_RE=re.compile(r"\$[0-9]+|%(?:[-+ #0]*[0-9]*(?:\.[0-9]+)?[A-Za-z%])|\\[A-Za-z][A-Za-z0-9_]*|\{[^{}\r\n]+\}|<[^<>\r\n]+>")
NUMBER_RE=re.compile(r"(?<!\$)[0-9\uff10-\uff19]+(?:[.,\uff0e\uff0c][0-9\uff10-\uff19]+)?")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
            json.dump(data,f,ensure_ascii=False,separators=(",",":"));f.write("\n")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def atomic_jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counters(pattern,text):
    return collections.Counter(pattern.findall(text))


def numbers(text):
    clean=TOKEN_RE.sub("",unicodedata.normalize("NFKC",text))
    return counters(NUMBER_RE,clean)


def ensure_packets(size=80):
    PACKETS.mkdir(parents=True,exist_ok=True)
    rows=[x for x in read_jsonl(SOURCE) if x["status"]=="review_complete"]
    ids=[x["source_id"] for x in rows]
    expected=[]
    for i,start in enumerate(range(0,len(rows),size),1):
        packet={"schema":"criminal-girls.non-bscr-integrated-review-packet.v2",
                "packet_id":f"non_bscr_review_{i:04d}","entry_count":len(rows[start:start+size]),
                "entries":rows[start:start+size]}
        path=PACKETS/f"packet_{i:04d}.json";atomic_json(path,packet);expected.append(path)
    for stale in PACKETS.glob("packet_*.json"):
        if stale not in expected:stale.unlink()
    manifest={"schema":"criminal-girls.non-bscr-review-manifest.v2","source":str(SOURCE),
              "source_sha256":sha(SOURCE),"translated_rows":len(rows),"source_ids_sha256":hashlib.sha256("\n".join(ids).encode()).hexdigest(),
              "packet_size":size,"packet_count":len(expected),
              "packets":[{"file":x.name,"sha256":sha(x),"entries":read_json(x)["entry_count"]} for x in expected]}
    atomic_json(OUTROOT/"packets_manifest.json",manifest)
    return expected


def validate_one(source,row):
    issues=[]
    if not isinstance(row,dict):return ["row_not_object"]
    if row.get("source_id")!=source["source_id"]:issues.append("source_id")
    target=row.get("target_ko")
    if not isinstance(target,str) or not target:return issues+["empty"]
    if "\0" in target:issues.append("nul")
    if JP_RE.search(target):issues.append("japanese_residue")
    if target.count("\n")!=source["source_ja"].count("\n") or target.count("\r")!=source["source_ja"].count("\r"):issues.append("newline")
    if counters(TOKEN_RE,target)!=counters(TOKEN_RE,source["source_ja"]):issues.append("tokens")
    if numbers(target)!=numbers(source["source_ja"]):issues.append("numbers")
    return issues


def validate_packet(packet,result):
    rows=result.get("rows") if isinstance(result,dict) else None
    if not isinstance(rows,list):return [],[{"code":"missing_rows"}]
    expected=packet["entries"]; by={}
    issues=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict):issues.append({"code":"row_not_object","index":i});continue
        sid=row.get("source_id")
        if sid in by:issues.append({"code":"duplicate","source_id":sid})
        elif isinstance(sid,str):by[sid]=row
    if [x.get("source_id") for x in rows if isinstance(x,dict)]!=[x["source_id"] for x in expected]:
        issues.append({"code":"order_or_set"})
    accepted=[]
    for source in expected:
        row=by.get(source["source_id"])
        if row is None:issues.append({"code":"missing","source_id":source["source_id"]});continue
        errs=validate_one(source,row)
        if errs:issues.extend({"code":x,"source_id":source["source_id"]} for x in errs)
        else:accepted.append({"source_id":source["source_id"],"target_ko":row["target_ko"]})
    return accepted,issues


def output_schema(path):
    atomic_json(path,{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object",
      "additionalProperties":False,"required":["rows"],"properties":{"rows":{"type":"array","items":{
      "type":"object","additionalProperties":False,"required":["source_id","target_ko"],
      "properties":{"source_id":{"type":"string","pattern":"^src_[0-9]{4}$"},"target_ko":{"type":"string","minLength":1}}}}}})


def compact(row):
    contexts=[]
    for c in row.get("contexts",[])[:4]:
        contexts.append({k:c[k] for k in ("uid","file","key","prev_source_ja","next_source_ja") if k in c})
    return {"source_id":row["source_id"],"source_ja":row["source_ja"],"reference_en":row.get("reference_en",""),
            "reference_variants":row.get("reference_variants",[]),"draft_ko":row["reviewed_ko"],
            "lanes":row.get("lanes",[]),"contexts":contexts}


def make_prompt(packet,issues):
    entries=packet["entries"]
    if issues:
        bad={x.get("source_id") for x in issues if x.get("source_id")}
        entries=[x for x in entries if x["source_id"] in bad]
    style=(PROJECT/"translation/bscr_v2/style_guide_bscr.md").read_text(encoding="utf-8-sig")
    glossary=(PROJECT/"translation/bscr_v2/glossary_bscr.json").read_text(encoding="utf-8-sig")
    retry=""
    if issues:retry="\nVALIDATION FAILURES TO REPAIR:\n"+json.dumps(issues,ensure_ascii=False,indent=2)
    return f"""Perform the one integrated final review of these Japanese-based Korean game strings.
Japanese is authoritative; English is reference-only. Independently verify each draft and correct meaning, omissions,
natural Korean, terminology, spacing, mechanics, tone, names, particles, and UI concision. Do not rubber-stamp drafts.
Use the locked terms in the glossary, including '벌주기', '걸즈 오더', '유대', and '옛 기억의 정원'.
Return every requested source_id exactly once in order. Preserve protected tokens, all Arabic numbers, and exact LF/CR counts.
Do not leave Japanese, add explanations, or output Markdown.
{retry}

STYLE GUIDE:
{style}

GLOSSARY:
{glossary}

INPUT:
{json.dumps({"packet_id":packet["packet_id"],"entries":[compact(x) for x in entries]},ensure_ascii=False,indent=2)}
"""


def invoke(path,args,repair=False):
    packet=read_json(path);result_path=RESULTS/path.name;invalid_path=INVALID/path.name
    prior=[]
    if repair:
        if not invalid_path.exists():return {"packet":path.name,"status":"no_invalid"}
        prior=read_json(invalid_path).get("issues",[])
    schema_path=OUTROOT/"result.schema.json";output_schema(schema_path)
    RESULTS.mkdir(parents=True,exist_ok=True);INVALID.mkdir(parents=True,exist_ok=True);LOGS.mkdir(parents=True,exist_ok=True)
    raw=result_path.with_suffix(".raw.tmp.json")
    cmd=[str(args.codex),"exec","-","-m",args.model,"-c",f'model_reasoning_effort="{args.reasoning}"',
         "-s","read-only","--skip-git-repo-check","--ephemeral","--output-schema",str(schema_path),
         "-o",str(raw),"-C",str(PROJECT),"--color","never"]
    started=time.time()
    proc=subprocess.run(cmd,input=make_prompt(packet,prior).encode("utf-8"),stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,timeout=args.timeout,check=False)
    (LOGS/(path.stem+(".repair.log" if repair else ".log"))).write_bytes(proc.stdout)
    if proc.returncode or not raw.exists():
        atomic_json(invalid_path,{"issues":[{"code":"codex_process"}]})
        return {"packet":path.name,"status":"process_failed","seconds":round(time.time()-started,1)}
    doc=read_json(raw);accepted,issues=validate_packet(packet,doc);raw.unlink(missing_ok=True)
    if repair and result_path.exists():
        old=read_json(result_path);old_rows=old.get("rows",[])
        source_by={x["source_id"]:x for x in packet["entries"]}
        good={x["source_id"]:x for x in old_rows if x.get("source_id") in source_by and not validate_one(source_by[x["source_id"]],x)}
        good.update({x["source_id"]:x for x in accepted})
        accepted=[good[x["source_id"]] for x in packet["entries"] if x["source_id"] in good]
        accepted,issues=validate_packet(packet,{"rows":accepted})
    atomic_json(result_path,{"rows":accepted})
    if issues:atomic_json(invalid_path,{"issues":issues,"accepted":len(accepted),"expected":packet["entry_count"]});status="needs_repair"
    else:invalid_path.unlink(missing_ok=True);status="ok"
    return {"packet":path.name,"status":status,"accepted":len(accepted),"issues":len(issues),"seconds":round(time.time()-started,1)}


def valid(path):
    result=RESULTS/path.name
    if not result.exists():return False
    a,i=validate_packet(read_json(path),read_json(result))
    return not i and len(a)==read_json(path)["entry_count"]


def finalize(paths):
    original=read_jsonl(SOURCE);reviewed={}
    for p in paths:
        for row in read_json(RESULTS/p.name)["rows"]:reviewed[row["source_id"]]=row["target_ko"]
    expected={x["source_id"] for x in original if x["status"]=="review_complete"}
    if set(reviewed)!=expected:raise RuntimeError(("coverage",len(reviewed),len(expected)))
    final=[]
    for row in original:
        out=dict(row)
        if out["status"]=="review_complete":
            out["reviewed_ko"]=reviewed[out["source_id"]]
            out["review_source"]="Codex internal model"
            out["review_pass"]="single_integrated_final_review_v2"
            out["final_review_provenance"]={"model":"gpt-5.5","method":"packetwise independent source/context review"}
        final.append(out)
    atomic_jsonl(FINAL,final)
    atomic_json(OUTROOT/"final_manifest.json",{"status":"PASS","rows":len(final),"reviewed":len(reviewed),
      "preserved":sum(x["status"]=="preserve" for x in final),"source_sha256":sha(SOURCE),"final_sha256":sha(FINAL)})
    return {"status":"PASS","rows":len(final),"reviewed":len(reviewed),"final":str(FINAL),"sha256":sha(FINAL)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--codex",type=Path,default=CODEX);ap.add_argument("--model",default="gpt-5.5")
    ap.add_argument("--reasoning",default="medium");ap.add_argument("--timeout",type=int,default=1800)
    ap.add_argument("--start",type=int,default=1);ap.add_argument("--end",type=int);ap.add_argument("--repair",action="store_true")
    ap.add_argument("--status",action="store_true");args=ap.parse_args();paths=ensure_packets()
    if args.status:
        print(json.dumps({"packets":len(paths),"valid":sum(valid(x) for x in paths),"invalid":sum((INVALID/x.name).exists() for x in paths),
          "missing":sum(not (RESULTS/x.name).exists() for x in paths)},ensure_ascii=False,indent=2));return 0
    failures=0
    for p in paths:
        n=int(p.stem.split("_")[-1])
        if n<args.start or (args.end and n>args.end):continue
        if args.repair and not (INVALID/p.name).exists():continue
        if not args.repair and valid(p):continue
        info=invoke(p,args,args.repair);print(json.dumps(info,ensure_ascii=False),flush=True)
        if info["status"]!="ok":failures+=1
    if all(valid(x) for x in paths):print(json.dumps(finalize(paths),ensure_ascii=False,indent=2))
    else:print(json.dumps({"complete":False,"valid":sum(valid(x) for x in paths),"packets":len(paths)},indent=2))
    return 1 if failures else 0


if __name__=="__main__":raise SystemExit(main())
