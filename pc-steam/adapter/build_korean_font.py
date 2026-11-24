#!/usr/bin/env python3
"""Build Korean-capable FNT files, runtime font slots, and ucs2jis mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HEADER = struct.Struct("<8I")


def parse_header(data: bytes):
    code_off,pal_bytes,bmp_bytes,code_bytes,extra_bytes,version,packed,bpp=HEADER.unpack_from(data,0)
    return {
        "code_off":code_off,"palette_bytes":pal_bytes,"bitmap_bytes":bmp_bytes,
        "code_bytes":code_bytes,"extra_bytes":extra_bytes,"version":version,
        "glyph_count":packed&0xFFFF,"width":(packed>>16)&0xFF,
        "height":(packed>>24)&0xFF,"bpp":bpp,"packed":packed,
        "bitmap_off":32+pal_bytes,
    }


def glyph_codes(data,h):
    return list(struct.unpack_from(f"<{h['glyph_count']}H",data,h["code_off"]))


def parse_runtime_font_bin(path):
    data=path.read_bytes()
    count=struct.unpack_from("<I",data,0)[0]
    if count!=2850 or len(data)!=4+count*4:
        raise ValueError(f"unexpected runtime font.bin layout: {count} records, {len(data)} bytes")
    records=[struct.unpack_from("<HBB",data,4+i*4) for i in range(count)]
    if [row[0] for row in records]!=sorted(row[0] for row in records):
        raise ValueError("runtime font.bin code table is not ascending")
    return data,records


def jis_to_sjis(jis:int)->int:
    a,b=jis>>8,jis&0xFF
    if not (0x21<=a<=0x7E and 0x21<=b<=0x7E):
        return jis
    lead=((a-0x21)>>1)+0x81
    if lead>0x9F: lead+=0x40
    if a&1:
        trail=b+0x1F
        if b>=0x60: trail+=1
    else:
        trail=b+0x7E
    return (lead<<8)|trail


def decode_sjis(code:int)->str|None:
    try:
        return code.to_bytes(2,"big").decode("cp932")
    except (UnicodeDecodeError,OverflowError):
        return None


def palette_alphas(data,h):
    raw=data[32:32+h["palette_bytes"]]
    return [raw[i*4+3] for i in range(1<<h["bpp"])]


def render_indices(ch, width, height, font_path, palette):
    font_size=max(5,width)
    font=ImageFont.truetype(str(font_path),font_size)
    try: font.set_variation_by_name("Medium")
    except OSError: pass
    bbox=font.getbbox(ch,anchor="lt")
    w=max(1,bbox[2]-bbox[0]); h=max(1,bbox[3]-bbox[1])
    # If a symbol exceeds the cell, reduce until it fits.
    while (w>width or h>height) and font_size>4:
        font_size-=1
        font=ImageFont.truetype(str(font_path),font_size)
        try: font.set_variation_by_name("Medium")
        except OSError: pass
        bbox=font.getbbox(ch,anchor="lt")
        w=max(1,bbox[2]-bbox[0]); h=max(1,bbox[3]-bbox[1])
    image=Image.new("L",(width,height),0)
    draw=ImageDraw.Draw(image)
    x=(width-w)//2-bbox[0]
    y=(height-h)//2-bbox[1]
    draw.text((x,y),ch,font=font,fill=255,anchor="lt")
    levels=list(enumerate(palette))
    return bytes(min(levels,key=lambda item:abs(item[1]-value))[0] for value in image.tobytes())


def pack_indices(indices,bpp):
    out=bytearray()
    if bpp==4:
        for i in range(0,len(indices),2):
            a=indices[i]; b=indices[i+1] if i+1<len(indices) else 0
            out.append((a<<4)|b)
    elif bpp==2:
        for i in range(0,len(indices),4):
            vals=list(indices[i:i+4])+[0,0,0,0]
            out.append((vals[0]<<6)|(vals[1]<<4)|(vals[2]<<2)|vals[3])
    else: raise NotImplementedError(bpp)
    return bytes(out)


def build_font(template,output,custom,slots,font_path):
    data=template.read_bytes(); h=parse_header(data); codes=glyph_codes(data,h)
    palette=palette_alphas(data,h)
    per=h["width"]*h["height"]*h["bpp"]//8
    generated={code:pack_indices(render_indices(ch,h["width"],h["height"],font_path,palette),h["bpp"]) for ch,code,_jis in custom}
    old_bitmap=data[h["bitmap_off"]:h["code_off"]]
    suffix=data[h["code_off"]+h["code_bytes"]:]
    if len(old_bitmap)!=h["glyph_count"]*per:
        raise ValueError(f"{template.name}: bitmap size does not match glyph count")

    # Replace existing slots byte-for-byte in place conceptually, then append only
    # runtime slots missing from this FNT.  Sorting preserves the binary-search
    # code-table contract and retains any pre-existing duplicate rows.
    records=[]
    existing=set(codes)
    replaced=set()
    for index,code in enumerate(codes):
        bitmap=old_bitmap[index*per:(index+1)*per]
        if code in generated:
            bitmap=generated[code]
            replaced.add(code)
        records.append((code,bitmap))
    appended=[]
    for _ch,code,_jis in custom:
        if code not in existing:
            records.append((code,generated[code]))
            existing.add(code)
            appended.append(code)
    records.sort(key=lambda item:item[0])

    new_count=len(records)
    if new_count>0xFFFF: raise ValueError("glyph count overflow")
    new_bitmap=b"".join(bitmap for _code,bitmap in records)
    new_codes=struct.pack(f"<{new_count}H",*(code for code,_bitmap in records))
    new_bmp_bytes=len(new_bitmap)
    new_code_off=h["bitmap_off"]+new_bmp_bytes
    new_code_bytes=len(new_codes)
    header=bytearray(data[:32])
    packed=(h["height"]<<24)|(h["width"]<<16)|new_count
    HEADER.pack_into(header,0,new_code_off,h["palette_bytes"],new_bmp_bytes,new_code_bytes,h["extra_bytes"],h["version"],packed,h["bpp"])
    palette_blob=data[32:h["bitmap_off"]]
    output.write_bytes(header+palette_blob+new_bitmap+new_codes+suffix)

    result=output.read_bytes(); oh=parse_header(result); result_codes=glyph_codes(result,oh); ocodes=set(result_codes)
    for _ch,code,_jis in custom:
        if code not in ocodes: raise ValueError(f"{output.name}: generated code missing {code:04X}")
    if result_codes!=sorted(result_codes):
        raise ValueError(f"{output.name}: glyph code table is not ascending")
    return {
        "name":output.name,
        "glyph_count_before":h["glyph_count"],
        "glyph_count_after":oh["glyph_count"],
        "size_before":len(data),
        "size_after":len(result),
        "custom_glyphs":len(custom),
        "replaced_existing_glyph_count":len(replaced),
        "appended_runtime_slot_count":len(appended),
        "code_table_ascending":True,
        "duplicate_code_count":len(result_codes)-len(ocodes),
    }


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_extra_texts(value):
    """Extract only Korean target leaves from supported JSON/JSONL shapes."""
    if isinstance(value, list):
        out=[]
        for item in value:
            out.extend(extract_extra_texts(item))
        return out
    if not isinstance(value, dict):
        return []
    for key in ("target_ko", "reviewed_ko"):
        target=value.get(key)
        if isinstance(target,str) and target:
            return [target]
    for key in ("rows", "entries"):
        nested=value.get(key)
        if isinstance(nested,list):
            return extract_extra_texts(nested)
    if value and all(isinstance(item,str) for item in value.values()):
        return list(value.values())
    return []


def read_extra_texts(path):
    if path.suffix.lower()==".jsonl":
        values=[json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    else:
        values=json.loads(path.read_text(encoding="utf-8-sig"))
    return extract_extra_texts(values)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reviewed",type=Path,required=True)
    ap.add_argument("--font-root",type=Path,required=True)
    ap.add_argument("--font-source",type=Path,required=True)
    ap.add_argument("--runtime-font-bin",type=Path,required=True)
    ap.add_argument("--output-root",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    ap.add_argument("--extra-text-json",type=Path,action="append",default=[])
    ap.add_argument("--preserve-text-json",type=Path,action="append",default=[])
    a=ap.parse_args()
    rows=[json.loads(x) for x in a.reviewed.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    texts=[r["reviewed_ko"] if r.get("status")=="review_complete" else r["source_ja"] for r in rows]
    extra_text_counts={}
    for path in a.extra_text_json:
        extra=read_extra_texts(path)
        texts.extend(extra)
        extra_text_counts[str(path)]=len(extra)
    preserve_text_counts={}
    preserve_chars=set()
    for path in a.preserve_text_json:
        value=json.loads(path.read_text(encoding="utf-8-sig"))
        preserved=[
            row["source_ja"]
            for row in value.get("rows",[])
            if row.get("preserved_original_japanese") is True and isinstance(row.get("source_ja"),str)
        ]
        if not preserved:
            raise ValueError(f"preserve-text authority contains no preserved source strings: {path}")
        texts.extend(preserved)
        chars=set("".join(preserved))
        preserve_chars.update(chars)
        preserve_text_counts[str(path)]={"text_count":len(preserved),"unique_character_count":len(chars)}
    all_chars=sorted(set("".join(texts)),key=ord)

    ucs_path=a.font_root/"ucs2jis.bin"
    ucs=bytearray(ucs_path.read_bytes())
    font_names=[f"if_fot0{i}.fnt" for i in range(1,6)]
    font_data={n:(a.font_root/n).read_bytes() for n in font_names}
    code_sets={n:set(glyph_codes(d,parse_header(d))) for n,d in font_data.items()}
    large_common=code_sets["if_fot01.fnt"]&code_sets["if_fot02.fnt"]
    runtime_font_data,runtime_records=parse_runtime_font_bin(a.runtime_font_bin)
    runtime_metrics={code:(index,metric0,metric1) for index,(code,metric0,metric1) in enumerate(runtime_records)}
    runtime_common=large_common&set(runtime_metrics)

    protected=set()
    custom_chars=[]
    for ch in all_chars:
        cp=ord(ch)
        if ch in "\r\n\t " or 0x20<=cp<=0x7E: continue
        jis=struct.unpack_from("<H",ucs,cp*2)[0]
        sjis=jis_to_sjis(jis) if jis else 0
        if jis and sjis in runtime_common:
            protected.add(sjis)
        else:
            custom_chars.append(ch)

    # Every source character that has a valid JIS mapping, is present in both
    # large FNTs and the outer runtime font, and is not needed by localized
    # text is repurposable.  Name composition needs the complete KS X 1001
    # Hangul set, so limiting this pool to already-full-width Kanji is too
    # narrow.  Selected outer metrics are normalized below without changing
    # record order or atlas geometry.
    candidates=[]
    original_fullwidth_candidates=0
    for code in sorted(runtime_metrics,reverse=True):
        ch=decode_sjis(code)
        if not ch or len(ch)!=1 or code in protected: continue
        runtime_index,metric0,metric1=runtime_metrics[code]
        cp=ord(ch)
        jis=struct.unpack_from("<H",ucs,cp*2)[0]
        if jis and jis_to_sjis(jis)==code:
            candidates.append((code,jis,ch))
            if metric1==48 and metric0<=2:
                original_fullwidth_candidates+=1
    if len(candidates)<len(custom_chars):
        raise ValueError(f"not enough repurposable runtime slots: {len(candidates)} < {len(custom_chars)}")
    selected=candidates[:len(custom_chars)]
    custom=[(ch,selected[i][0],selected[i][1]) for i,ch in enumerate(custom_chars)]
    selected_codes={code for code,_jis,_former in selected}
    preserve_runtime_slots=[]
    for ch in sorted(preserve_chars,key=ord):
        cp=ord(ch)
        if ch in "\r\n\t " or 0x20<=cp<=0x7E:
            continue
        jis=struct.unpack_from("<H",ucs,cp*2)[0]
        code=jis_to_sjis(jis) if jis else 0
        if not code or code not in runtime_metrics:
            raise ValueError(f"preserved selector glyph is absent from runtime font: {ch!r}")
        if code in selected_codes:
            raise ValueError(f"preserved selector glyph was selected for repurposing: {ch!r}/{code:04X}")
        index,metric0,metric1=runtime_metrics[code]
        preserve_runtime_slots.append({
            "char":ch,
            "sjis":f"{code:04X}",
            "jis":f"{jis:04X}",
            "runtime_font_index":index,
            "runtime_font_page":index//648,
            "runtime_font_cell":index%648,
            "metric0":metric0,
            "metric1":metric1,
        })

    for ch,code,jis in custom:
        struct.pack_into("<H",ucs,ord(ch)*2,jis)

    a.output_root.mkdir(parents=True,exist_ok=True)
    out_ucs=a.output_root/"ucs2jis.bin"
    out_ucs.write_bytes(ucs)

    # Preserve font.bin's 2,850-record order (the atlas cell index contract)
    # and normalize only the metrics of allowlisted repurposed slots.
    patched_runtime_font=bytearray(runtime_font_data)
    runtime_metric_changes=0
    for _ch,code,_jis in custom:
        runtime_index,metric0,metric1=runtime_metrics[code]
        if (metric0,metric1)!=(1,48):
            runtime_metric_changes+=1
        struct.pack_into("<HBB",patched_runtime_font,4+runtime_index*4,code,1,48)
    out_runtime_font=a.output_root/"font.bin"
    out_runtime_font.write_bytes(patched_runtime_font)
    mapped_nonascii=[]
    seen_codes=set()
    for ch in all_chars:
        cp=ord(ch)
        if ch in "\r\n\t " or 0x20<=cp<=0x7E: continue
        jis=struct.unpack_from("<H",ucs,cp*2)[0]
        sjis=jis_to_sjis(jis) if jis else 0
        if jis and sjis not in seen_codes:
            mapped_nonascii.append((ch,sjis,jis))
            seen_codes.add(sjis)

    fonts=[]
    for name in font_names:
        additions=custom if name in {"if_fot01.fnt","if_fot02.fnt"} else mapped_nonascii
        fonts.append(build_font(a.font_root/name,a.output_root/name,additions,selected,a.font_source))

    # Global verification: every non-ASCII character in localized text maps
    # to a code present in every generated font that can carry non-ASCII.
    generated_sets={}
    for name in font_names:
        d=(a.output_root/name).read_bytes()
        generated_sets[name]=set(glyph_codes(d,parse_header(d)))
    unsupported=[]
    for ch in all_chars:
        cp=ord(ch)
        if ch in "\r\n\t " or 0x20<=cp<=0x7E: continue
        jis=struct.unpack_from("<H",ucs,cp*2)[0]
        sjis=jis_to_sjis(jis) if jis else 0
        if not jis or any(sjis not in s for s in generated_sets.values()):
            unsupported.append({"char":ch,"codepoint":f"U+{cp:04X}","jis":f"{jis:04X}","sjis":f"{sjis:04X}"})
    report={
        "font_source":str(a.font_source),
        "runtime_font_bin":str(a.runtime_font_bin),
        "runtime_font_bin_sha256":hashlib.sha256(runtime_font_data).hexdigest(),
        "runtime_font_record_count":len(runtime_records),
        "runtime_fnt_common_code_count":len(runtime_common),
        "runtime_original_fullwidth_candidate_count":original_fullwidth_candidates,
        "runtime_repurposable_candidate_count":len(candidates),
        "selected_slot_count_absent_from_large_fnt_common":sum(code not in large_common for code,_jis,_former in selected),
        "preserve_text_sources":[
            {"path":str(path),"sha256":sha256(path),**preserve_text_counts[str(path)]}
            for path in a.preserve_text_json
        ],
        "preserved_text_unique_character_count":len(preserve_chars),
        "preserved_runtime_slot_count":len(preserve_runtime_slots),
        "preserved_runtime_slots":preserve_runtime_slots,
        "runtime_font_bin_output":str(out_runtime_font),
        "runtime_font_bin_output_sha256":sha256(out_runtime_font),
        "runtime_metric_changed_record_count":runtime_metric_changes,
        "runtime_record_order_preserved":True,
        "extra_text_sources":[{"path":str(path),"sha256":sha256(path),"text_count":extra_text_counts[str(path)]} for path in a.extra_text_json],
        "required_character_count":len(all_chars),
        "custom_character_count":len(custom),
        "hangul_syllable_count":sum(0xAC00<=ord(ch)<=0xD7A3 for ch in custom_chars),
        "custom_characters":"".join(custom_chars),
        "repurposed_slots":[{
            "char":ch,"sjis":f"{code:04X}","jis":f"{jis:04X}","former_char":decode_sjis(code),
            "runtime_font_index":runtime_metrics[code][0],
            "runtime_font_page":runtime_metrics[code][0]//648,
            "runtime_font_cell":runtime_metrics[code][0]%648,
            "runtime_metric0_original":runtime_metrics[code][1],
            "runtime_metric1_original":runtime_metrics[code][2],
            "runtime_metric0":1,
            "runtime_metric1":48,
        } for ch,code,jis in custom],
        "unsupported":unsupported,
        "fonts":fonts,
        "ucs2jis_sha256":sha256(out_ucs),
        "passed":not unsupported,
    }
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in {"repurposed_slots","preserved_runtime_slots","custom_characters","fonts"}},ensure_ascii=False,indent=2))
    print(json.dumps({"fonts":fonts},ensure_ascii=False,indent=2))
    if unsupported: raise SystemExit(1)

if __name__=="__main__": main()

