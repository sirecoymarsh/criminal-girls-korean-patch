#!/usr/bin/env python3
from pathlib import Path
import sys,json
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(r'P:\AI\Codex\projects\criminal-girls-invite-only-ko')
sys.path.insert(0,str(ROOT/'adapter'))
from imy_tool import decode_imy,indexed_to_rgba,direct_to_rgba
OUT=ROOT/'ui_review/full_audit/decoded'; OUT.mkdir(parents=True,exist_ok=True)
diff=json.loads((ROOT/'audit/jp_vs_en_payload_diff.json').read_text(encoding='utf-8-sig'))['differences']
names=sorted({x['name'] for x in diff if x['extension']=='.imy'})
assets=[(n,ROOT/'extracted/ui_imy/jp'/n,ROOT/'extracted/ui_imy/en'/n,'outer_imy') for n in names]
assets += [
('system__fl_ui00.ptm',ROOT/'extracted/nested/jp/system.tpk/fl_ui00.ptm',ROOT/'extracted/nested/en/system.tpk/fl_ui00.ptm','system_ptm'),
('system__fl_ui01.ptm',ROOT/'extracted/nested/jp/system.tpk/fl_ui01.ptm',ROOT/'extracted/nested/en/system.tpk/fl_ui01.ptm','system_ptm'),
('system__st_ui00.ptm',ROOT/'extracted/nested/jp/system.tpk/st_ui00.ptm',ROOT/'extracted/nested/en/system.tpk/st_ui00.ptm','system_ptm'),
('system__st_ui01.ptm',ROOT/'extracted/nested/jp/system.tpk/st_ui01.ptm',ROOT/'extracted/nested/en/system.tpk/st_ui01.ptm','system_ptm'),
('system__st_ui02.ptm',ROOT/'extracted/nested/jp/system.tpk/st_ui02.ptm',ROOT/'extracted/nested/en/system.tpk/st_ui02.ptm','system_ptm'),
('camp__os_01_00.ptm',ROOT/'extracted/text_extra/jp/payloads/if_camp_res.tpk/os_01_00.ptm',ROOT/'extracted/text_extra/en/payloads/if_camp_res.tpk/os_01_00.ptm','camp_ptm'),
('systemvol__if_emo01.ptm',ROOT/'extracted/recursive/jp/system.tpk/system.vol/if_emo01.ptm',ROOT/'extracted/recursive/en/system.tpk/system.vol/if_emo01.ptm','system_vol_ptm')]
def dec(p):
 src=p.read_bytes(); h,raw=decode_imy(src)
 if h.palette_size: rgba=indexed_to_rgba(raw,src[32:32+h.palette_size*4],'bgra',False); size=(h.stride,h.height)
 else: rgba=direct_to_rgba(raw,'bgra',False); size=(h.stride//4,h.height)
 return h,Image.frombytes('RGBA',size,rgba)
meta=[]; pairs=[]
for label,jp,en,kind in assets:
 safe=label.replace('.','_'); jp_png=OUT/f'{safe}__jp.png'; en_png=OUT/f'{safe}__en.png'
 hj,ji=dec(jp); he,ei=dec(en)
 ji.save(jp_png,optimize=True); ei.save(en_png,optimize=True)
 meta.append({'label':label,'kind':kind,'jp':str(jp),'en':str(en),'size':ji.size,'jp_header':hj.__dict__,'en_header':he.__dict__}); pairs.append((label,ji,ei))
font=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',20); page_dir=ROOT/'ui_review/full_audit/sheets'; page_dir.mkdir(parents=True,exist_ok=True)
for old in page_dir.glob('ui_audit_page_*.jpg'): old.unlink()
for page_no,start in enumerate(range(0,len(pairs),6),1):
 subset=pairs[start:start+6]; cellw=760; cellh=400; sheet=Image.new('RGB',(cellw*2,cellh*len(subset)),(30,30,34)); d=ImageDraw.Draw(sheet)
 for row,(label,ji,ei) in enumerate(subset):
  for col,(tag,im) in enumerate([('JP',ji),('EN',ei)]):
   comp=Image.new('RGBA',im.size,(18,18,22,255)); comp.alpha_composite(im); comp.thumbnail((cellw-20,cellh-55),Image.Resampling.LANCZOS)
   x=col*cellw+(cellw-comp.width)//2; y=row*cellh+42+(cellh-48-comp.height)//2
   sheet.paste(comp.convert('RGB'),(x,y)); d.text((col*cellw+10,row*cellh+10),f'{label} [{tag}] {im.width}x{im.height}',font=font,fill=(245,245,245))
 path=page_dir/f'ui_audit_page_{page_no:02d}.jpg'; sheet.save(path,quality=88,optimize=True); print(path)
(ROOT/'ui_review/full_audit/asset_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'assets':len(assets),'pages':(len(assets)+5)//6}))
