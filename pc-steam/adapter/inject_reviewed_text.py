#!/usr/bin/env python3
"""Inject reviewed Korean text into extracted Criminal Girls text payloads."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import struct
from pathlib import Path

from runtime_text_codec import RuntimeTextCodec, load_runtime_text_codec

KEY_SIZE = 28
KEY_RECORD_SIZE = 32


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        while chunk:=f.read(1024*1024): h.update(chunk)
    return h.hexdigest()


def align4_extra(position: int) -> int:
    # Original tables always advance to the *next* 4-byte boundary.
    return ((position // 4) + 1) * 4


def parse_keyed_raw(path: Path):
    blob=path.read_bytes()
    count=struct.unpack_from("<I",blob,0)[0]
    table_end=4+count*KEY_RECORD_SIZE
    records=[]
    for i in range(count):
        pos=4+i*KEY_RECORD_SIZE
        offset=struct.unpack_from("<I",blob,pos)[0]
        key_raw=blob[pos+4:pos+KEY_RECORD_SIZE]
        key=key_raw.split(b"\0",1)[0].decode("ascii")
        records.append({"index":i,"record_pos":pos,"offset":offset,"key_raw":key_raw,"key":key})
    offsets=sorted({r["offset"] for r in records})
    ends={o:(offsets[i+1] if i+1<len(offsets) else len(blob)) for i,o in enumerate(offsets)}
    for r in records:
        r["span"]=blob[r["offset"]:ends[r["offset"]]]
        r["value"]=r["span"].rstrip(b"\0")
        r["binary"]=r["key"].endswith("_NUM") or r["key"].endswith("[]")
    return blob,records,table_end


def build_keyed(template: Path, output: Path, text_by_index: dict[int,str], codec: RuntimeTextCodec) -> dict:
    blob,records,table_end=parse_keyed_raw(template)
    for index in text_by_index:
        if records[index]["binary"]:
            raise ValueError(f"refusing to translate binary record {template}:{index}:{records[index]['key']}")

    # First pass: compute every new record offset. Binary lookup tables can
    # only be repaired once the complete old->new address map is known.
    chunks:dict[int,bytes]={}
    offsets:dict[int,int]={}
    cursor=table_end
    for r in records:
        offsets[r["index"]]=cursor
        if r["index"] in text_by_index:
            raw=codec.encode_bytes(text_by_index[r["index"]])
            pad=align4_extra(cursor+len(raw))-(cursor+len(raw))
            chunk=raw+b"\0"*pad
        else:
            chunk=r["span"]
        chunks[r["index"]]=chunk
        cursor+=len(chunk)

    old_to_new={r["offset"]:offsets[r["index"]] for r in records}
    pointer_word_count=0
    relocated_pointer_count=0
    pointer_records=[]
    for r in records:
        if not r["binary"]:
            continue
        chunk=bytearray(chunks[r["index"]])
        record_words=0
        record_relocated=0
        for pos in range(0,len(chunk)-3,4):
            old=struct.unpack_from("<I",chunk,pos)[0]
            if old not in old_to_new:
                continue
            new=old_to_new[old]
            struct.pack_into("<I",chunk,pos,new)
            pointer_word_count+=1
            record_words+=1
            if new!=old:
                relocated_pointer_count+=1
                record_relocated+=1
        if record_words:
            pointer_records.append({
                "index":r["index"],"key":r["key"],
                "pointer_words":record_words,"relocated_words":record_relocated,
            })
        chunks[r["index"]]=bytes(chunk)

    body=bytearray()
    for r in records:
        if table_end+len(body)!=offsets[r["index"]]:
            raise AssertionError((template,r["index"],table_end+len(body),offsets[r["index"]]))
        body.extend(chunks[r["index"]])
    header=bytearray(blob[:table_end])
    for r in records:
        struct.pack_into("<I",header,r["record_pos"],offsets[r["index"]])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(header+body)

    # Verify translated strings and every detected embedded record pointer
    # through a fresh parse of the rebuilt file.
    _out_blob,out_records,_=parse_keyed_raw(output)
    for index,text in text_by_index.items():
        got=out_records[index]["value"].decode("utf-8")
        if got!=codec.encode_text(text) or codec.decode_text(got)!=text:
            raise ValueError(f"keyed runtime-codec verification failed {template}:{index}")
    for item in pointer_records:
        index=item["index"]
        original=records[index]["span"]
        rebuilt=out_records[index]["span"]
        for pos in range(0,len(original)-3,4):
            old=struct.unpack_from("<I",original,pos)[0]
            if old in old_to_new:
                got=struct.unpack_from("<I",rebuilt,pos)[0]
                if got!=old_to_new[old]:
                    raise ValueError(
                        f"pointer relocation verification failed {template}:{index}:{pos}: "
                        f"{got} != {old_to_new[old]}"
                    )
    return {
        "kind":"keyed","record_count":len(records),
        "translated_records":len(text_by_index),
        "size_before":len(blob),"size_after":output.stat().st_size,
        "pointer_word_count":pointer_word_count,
        "relocated_pointer_count":relocated_pointer_count,
        "pointer_record_count":len(pointer_records),
        "pointer_records":pointer_records,
    }


def build_keyed_inplace(template: Path, output: Path, text_by_index: dict[int,str], codec: RuntimeTextCodec) -> dict:
    """Replace keyed UTF-8 values without moving any record or changing file size.

    title/option.asbin may retain offsets into option.dat. Rebuilding option.dat and
    relocating only its internal tables passed static checks but crashed the retail
    executable at RVA 0xD11E8. Preserve every header offset and record span exactly.
    """
    blob,records,table_end=parse_keyed_raw(template)
    rebuilt=bytearray(blob)
    for index,text in text_by_index.items():
        r=records[index]
        if r["binary"]:
            raise ValueError(f"refusing to translate binary record {template}:{index}:{r['key']}")
        raw=codec.encode_bytes(text)
        span_len=len(r["span"])
        if len(raw)+1 > span_len:
            raise ValueError(
                f"fixed keyed slot overflow {template}:{index}:{r['key']}: "
                f"{len(raw)+1} > {span_len}"
            )
        start=r["offset"]
        rebuilt[start:start+span_len]=raw+b"\0"*(span_len-len(raw))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(rebuilt)
    out_blob,out_records,out_table_end=parse_keyed_raw(output)
    if len(out_blob)!=len(blob) or out_table_end!=table_end:
        raise ValueError(f"fixed keyed layout changed {template}")
    for before,after in zip(records,out_records):
        if before["offset"]!=after["offset"] or before["record_pos"]!=after["record_pos"]:
            raise ValueError(f"fixed keyed offset changed {template}:{before['index']}")
    for index,text in text_by_index.items():
        got=out_records[index]["value"].decode("utf-8")
        if got!=codec.encode_text(text) or codec.decode_text(got)!=text:
            raise ValueError(f"fixed keyed runtime-codec verification failed {template}:{index}")
    return {
        "kind":"keyed_inplace","record_count":len(records),
        "translated_records":len(text_by_index),
        "size_before":len(blob),"size_after":len(out_blob),
        "pointer_word_count":0,"relocated_pointer_count":0,
        "pointer_record_count":0,"pointer_records":[],
        "all_record_offsets_preserved":True,
    }


def parse_unkeyed_raw(path: Path):
    blob=path.read_bytes()
    body_size=struct.unpack_from("<I",blob,0)[0]
    body=blob[4:4+body_size]
    strings=body.decode("utf-8").split("\0")
    while strings and strings[-1]=="": strings.pop()
    return blob,strings,blob[4+body_size:]


def build_unkeyed(template: Path, output: Path, text_by_index: dict[int,str], codec: RuntimeTextCodec) -> dict:
    blob,strings,tail=parse_unkeyed_raw(template)
    for index,text in text_by_index.items():
        if not 0<=index<len(strings): raise IndexError((template,index,len(strings)))
        strings[index]=codec.encode_text(text)
    body=("\0".join(strings)+"\0").encode("utf-8")
    pad=(-len(body))%4
    rebuilt=struct.pack("<I",len(body))+body+b"\0"*pad
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(rebuilt)
    _b,check,_t=parse_unkeyed_raw(output)
    if check!=strings: raise ValueError(f"unkeyed verification failed {template}")
    for index,text in text_by_index.items():
        if codec.decode_text(check[index])!=text:
            raise ValueError(f"unkeyed runtime-codec verification failed {template}:{index}")
    return {"kind":"unkeyed","record_count":len(strings),"translated_records":len(text_by_index),"size_before":len(blob),"size_after":len(rebuilt)}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog",type=Path,required=True)
    ap.add_argument("--reviewed",type=Path,required=True)
    ap.add_argument("--field-root",type=Path,required=True)
    ap.add_argument("--battle-root",type=Path,required=True)
    ap.add_argument("--system-file",type=Path,required=True)
    ap.add_argument("--punishment-file",type=Path,required=True)
    ap.add_argument("--camp-file",type=Path,required=True)
    ap.add_argument("--option-file",type=Path,required=True)
    ap.add_argument("--font-report",type=Path,required=True)
    ap.add_argument("--output-root",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    codec=load_runtime_text_codec(a.font_report)

    catalog=[json.loads(x) for x in a.catalog.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    unique=[json.loads(x) for x in a.reviewed.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    source_map={}
    reviewed_rows=[r for r in unique if r.get("status")=="review_complete"]
    preserve_rows=[r for r in unique if r.get("status")=="preserve"]
    for r in reviewed_rows:
        source=r["source_ja"]
        target=r["reviewed_ko"]
        if source in source_map and source_map[source]!=target:
            raise ValueError(f"conflicting reviewed translations for source {source!r}")
        source_map[source]=target
    if len(unique)!=2709:
        raise ValueError(f"expected 2709 final rows, got {len(unique)}")
    if len(reviewed_rows)!=2639 or len(preserve_rows)!=70:
        raise ValueError(
            f"expected 2639 reviewed / 70 preserved rows, got {len(reviewed_rows)} / {len(preserve_rows)}"
        )
    if len(source_map)!=len(reviewed_rows):
        raise ValueError(f"reviewed source identity is not unique: {len(source_map)} / {len(reviewed_rows)}")

    jobs=collections.defaultdict(dict)
    occurrence_count=0
    for r in catalog:
        source=r["source_ja"]
        if source not in source_map: continue
        key=(r["lane"],r["file"])
        index=int(r["record_index"])
        text=source_map[source]
        if index in jobs[key] and jobs[key][index]!=text:
            raise ValueError(f"conflicting occurrence {key}:{index}")
        jobs[key][index]=text
        occurrence_count+=1

    def locate(lane,file):
        if lane=="field_message": return a.field_root.joinpath(*Path(file).parts)
        if lane=="battle_text": return a.battle_root/file
        if lane=="system_text": return a.system_file
        if lane=="punishment_text": return a.punishment_file
        if lane=="camp_text": return a.camp_file
        if lane=="title_option_text": return a.option_file
        raise ValueError(lane)

    files=[]
    for (lane,file),mapping in sorted(jobs.items()):
        src=locate(lane,file)
        if not src.is_file(): raise FileNotFoundError(src)
        rel=Path(lane).joinpath(*Path(file).parts)
        dst=a.output_root/rel
        if lane=="battle_text":
            meta=build_unkeyed(src,dst,mapping,codec)
        elif lane=="title_option_text":
            meta=build_keyed_inplace(src,dst,mapping,codec)
        else:
            meta=build_keyed(src,dst,mapping,codec)
        meta.update(lane=lane,file=file,source=str(src),output=str(dst),sha256=sha256(dst))
        files.append(meta)

    summary={
        "reviewed_unique_strings":len(source_map),
        "translated_occurrences":occurrence_count,
        "output_file_count":len(files),
        "runtime_text_encoding":"utf8_former_character_glyph_slots",
        "font_report":str(a.font_report),
        "font_report_sha256":codec.font_report_sha256,
        "runtime_surrogate_slot_count":len(codec.char_to_former),
        "runtime_surrogate_occurrences":sum(codec.surrogate_count(text) for mapping in jobs.values() for text in mapping.values()),
        "lane_file_counts":dict(collections.Counter(x["lane"] for x in files)),
        "translated_record_counts":dict(collections.Counter({lane:sum(x["translated_records"] for x in files if x["lane"]==lane) for lane in {x["lane"] for x in files}})),
        "files":files,
    }
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="files"},ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())

