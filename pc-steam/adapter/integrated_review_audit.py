#!/usr/bin/env python3
import argparse, json, re
from pathlib import Path

TERMS = {
    "おしおき": ("벌주기",),
    "更生": ("갱생",),
    "囚監フロア": ("수감동",),
    "泥ノ試練": ("진흙의 시련",),
    "炎ノ試練": ("불꽃의 시련",),
    "氷ノ試練": ("얼음의 시련",),
    "古き記憶の園": ("오래된 기억의 정원",),
    "少女地獄": ("소녀 지옥",),
    "クリミナル": ("크리미널",),
    "キズナ": ("유대",),
}
PARTICLE_RE = re.compile(r"(?:은\(는\)|이\(가\)|을\(를\)|과\(와\)|으\(로\))")
CJK_RE = re.compile(r"[一-龯々〆〤]")
KANA_RE = re.compile(r"[ぁ-ゖァ-ヺ]")
FULLWIDTH_ALNUM_RE = re.compile(r"[Ａ-Ｚａ-ｚ０-９]")
PAIR_CHARS = [("【","】"),("「","」"),("『","』"),("(",")")]

def compact(s):
    return s.replace("\r", "").replace("\n", "\\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("outdir", type=Path)
    a = ap.parse_args()
    rows = [json.loads(x) for x in a.input.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    rows = [r for r in rows if r.get("status") == "draft_complete"]
    buckets = {k: [] for k in [
        "cjk_remaining", "kana_remaining", "fullwidth_alnum", "same_as_source",
        "particle_placeholders", "newline_mismatch", "length_outliers",
        "bracket_mismatch", "term_mismatch", "leading_trailing_space"
    ]}
    for r in rows:
        sid, ja, ko = r["source_id"], r.get("source_ja", ""), r.get("draft_ko", "")
        item = {"source_id": sid, "source_ja": ja, "draft_ko": ko, "lanes": r.get("lanes", [])}
        if CJK_RE.search(ko): buckets["cjk_remaining"].append(item)
        if KANA_RE.search(ko): buckets["kana_remaining"].append(item)
        if FULLWIDTH_ALNUM_RE.search(ko): buckets["fullwidth_alnum"].append(item)
        if ja == ko: buckets["same_as_source"].append(item)
        if PARTICLE_RE.search(ko): buckets["particle_placeholders"].append(item)
        if ja.count("\n") != ko.count("\n"): buckets["newline_mismatch"].append(item)
        ja_len = len(re.sub(r"\s+", "", ja))
        ko_len = len(re.sub(r"\s+", "", ko))
        ratio = ko_len / max(1, ja_len)
        if (ja_len >= 4 and ratio > 2.0) or (ja_len >= 8 and ratio < 0.42):
            item = dict(item, ja_len=ja_len, ko_len=ko_len, ratio=round(ratio, 3))
            buckets["length_outliers"].append(item)
        if any(ko.count(x) != ko.count(y) for x,y in PAIR_CHARS):
            buckets["bracket_mismatch"].append(item)
        for src, expected in TERMS.items():
            if src in ja and not any(x in ko for x in expected):
                buckets["term_mismatch"].append(dict(item, source_term=src, expected=list(expected)))
        if ko != ko.strip():
            buckets["leading_trailing_space"].append(item)
    a.outdir.mkdir(parents=True, exist_ok=True)
    summary = {
        "stage": "integrated_review",
        "review_scope": len(rows),
        "counts": {k: len(v) for k,v in buckets.items()},
    }
    (a.outdir / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for name, items in buckets.items():
        with (a.outdir / f"{name}.tsv").open("w", encoding="utf-8", newline="") as f:
            f.write("source_id\tsource_ja\tdraft_ko\tmeta\n")
            for item in items:
                meta = {k:v for k,v in item.items() if k not in ("source_id","source_ja","draft_ko")}
                f.write(f"{item['source_id']}\t{compact(item['source_ja'])}\t{compact(item['draft_ko'])}\t{json.dumps(meta, ensure_ascii=False)}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
