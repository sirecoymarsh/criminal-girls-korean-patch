#!/usr/bin/env python3
import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("input",type=Path)
    ap.add_argument("overrides",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--changes",type=Path,required=True)
    ap.add_argument("--summary",type=Path,required=True)
    a=ap.parse_args()
    rows=[json.loads(x) for x in a.input.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    doc=json.loads(a.overrides.read_text(encoding="utf-8-sig"))
    ov=doc["translations"]
    by_id={r["source_id"]:r for r in rows}
    unknown=sorted(set(ov)-set(by_id))
    if unknown: raise SystemExit(f"unknown source ids: {unknown}")
    changes=[]
    reviewed=0
    for r in rows:
        if r.get("status")=="draft_complete":
            sid=r["source_id"]
            before=r["draft_ko"]
            after=ov.get(sid,before)
            if not after: raise SystemExit(f"empty reviewed translation: {sid}")
            r["reviewed_ko"]=after
            r["status"]="review_complete"
            r["review_source"]="Codex internal model"
            r["review_pass"]="single_integrated_review"
            reviewed+=1
            if before!=after:
                changes.append({"source_id":sid,"source_ja":r.get("source_ja",""),"before":before,"after":after})
    counts={}
    for r in rows: counts[r["status"]]=counts.get(r["status"],0)+1
    summary={
        "total_unique":len(rows),
        "reviewed_translations":reviewed,
        "overrides_applied":len(changes),
        "status_counts":counts,
        "integrated_review_started":True,
        "integrated_review_complete":reviewed==2637 and counts.get("preserve")==72,
        "reviewer":"Codex internal model",
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
    a.changes.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in changes),encoding="utf-8")
    a.summary.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
