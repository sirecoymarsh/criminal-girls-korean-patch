#!/usr/bin/env python3
import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('catalog',type=Path)
    ap.add_argument('draft',type=Path,nargs='+')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--summary',type=Path,required=True)
    a=ap.parse_args()
    rows=[json.loads(x) for x in a.catalog.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    by_id={r['source_id']:r for r in rows}
    seen={}
    for p in a.draft:
        doc=json.loads(p.read_text(encoding='utf-8-sig'))
        for sid,ko in doc['translations'].items():
            if sid not in by_id: raise SystemExit(f'unknown source_id {sid} in {p}')
            if sid in seen and seen[sid]!=ko: raise SystemExit(f'conflicting translation {sid}')
            if not ko: raise SystemExit(f'empty translation {sid}')
            seen[sid]=ko
    for sid,ko in seen.items():
        by_id[sid]['draft_ko']=ko
        by_id[sid]['status']='draft_complete'
        by_id[sid]['draft_source']='Codex internal model'
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    counts={}
    for r in rows: counts[r['status']]=counts.get(r['status'],0)+1
    summary={'total_unique':len(rows),'applied_translations':len(seen),'status_counts':counts,'integrated_review_started':False}
    a.summary.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()