#!/usr/bin/env python3
"""Build localized nested containers from reviewed text and Korean fonts."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from archive_repack import parse_template, repack


def make_manifest(template:Path,replacements:dict[str,Path],path:Path)->Path:
    entries,_,_=parse_template(template,"dsarcidx")
    by_name=collections.defaultdict(list)
    for e in entries: by_name[e.name].append(e)
    items=[]
    for name,payload in sorted(replacements.items()):
        found=by_name.get(name,[])
        if len(found)!=1:
            raise ValueError(f"{template}: expected one {name!r}, got {len(found)}")
        items.append({"index":found[0].index,"expected_name":name,"path":str(payload)})
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"template":str(template),"replacements":items},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return path


def build_one(name,template,replacements,output,manifests,reports):
    manifest=make_manifest(template,replacements,manifests/f"{name}.replacements.json")
    report=reports/f"{name}.json"
    result=repack(template,output,"dsarcidx",manifest)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    root=a.root
    localized=root/"staging/localized_text"
    out=root/"staging/containers"
    manifests=root/"staging/manifests/nested"
    reports=root/"staging/reports/nested"
    results=[]

    # 105 field-message containers.
    for template in sorted((root/"extracted/field_messages/jp/containers").glob("field_mess*.tpk")):
        stem=template.stem
        replacement=localized/"field_message"/stem/f"{stem}.dat"
        results.append(build_one(
            f"field_{stem}",template,{f"{stem}.dat":replacement},
            out/"field"/template.name,manifests,reports))

    battle_replacements={p.name:p for p in sorted((localized/"battle_text").glob("*.utf8"))}
    results.append(build_one(
        "btl_allparam",
        root/"extracted/pilot/jp/btl_allparam.tpk",
        battle_replacements,
        out/"btl_allparam.tpk",manifests,reports))

    font_replacements={p.name:p for p in sorted((root/"staging/korean_font").glob("*")) if p.suffix == ".fnt" or p.name == "ucs2jis.bin"}
    results.append(build_one(
        "system_vol",
        root/"extracted/nested/jp/system.tpk/system.vol",
        font_replacements,
        out/"system.vol",manifests,reports))

    results.append(build_one(
        "system",
        root/"extracted/pilot/jp/system.tpk",
        {
            "system.vol":out/"system.vol",
            "system_txt.dat":localized/"system_text/system_txt.dat",
            **{p.name:p for p in sorted((root/"staging/ui_encoded/system").glob("*.ptm"))},
        },
        out/"system.tpk",manifests,reports))

    results.append(build_one(
        "if_camp_res",
        root/"extracted/text_extra/jp/containers/if_camp_res.tpk",
        {
            "oshioki_txt.dat":localized/"punishment_text/oshioki_txt.dat",
            "camp_txt.dat":localized/"camp_text/camp_txt.dat",
        },
        out/"if_camp_res.tpk",manifests,reports))

    results.append(build_one(
        "title",
        root/"extracted/text_extra/jp/containers/title.tpk",
        {"option.dat":localized/"title_option_text/option.dat"},
        out/"title.tpk",manifests,reports))

    summary={
        "container_count":len(results),
        "field_container_count":sum("field_mess" in r["output"] for r in results),
        "replacement_payload_count":sum(r["replacement_count"] for r in results),
        "all_replacements_verified":all(len(r["verified_replacements"])==r["replacement_count"] for r in results),
        "containers":results,
    }
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="containers"},ensure_ascii=False,indent=2))
    if not summary["all_replacements_verified"]: raise SystemExit(1)

if __name__=="__main__": main()

