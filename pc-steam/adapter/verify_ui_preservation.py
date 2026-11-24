from pathlib import Path
import json
import numpy as np
from PIL import Image
ROOT=Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
JP=ROOT/"ui_review/full_audit/decoded"; KO=ROOT/"ui_review/full_mockups/assets"
manifest=json.loads((ROOT/"ui_review/full_mockups/manifest.json").read_text(encoding="utf-8"))
B={
"bt_ui_00_0000_imy":[(0,340,340,515),(220,380,512,520),(0,500,780,710)],
"bt_ui_01_0000_imy":[(0,630,580,735),(0,920,390,1024)],
"bt_ui_02_0000_imy":[(0,185,290,390)],
"bt_ui_07_0000_imy":[(0,35,150,110),(0,100,310,220),(180,230,512,380),(0,410,330,505)],
"bt_ui_07_0001_imy":[(0,185,290,390)],
"fl_ui03_imy":[(190,0,455,515),(140,410,790,600)],
"ic000_001_0000_00_imy":[(10,0,310,95)],
"ic000_002_0000_00_imy":[(10,0,310,95)],
"ic000_003_0000_00_imy":[(10,0,310,80),(220,45,512,128)],
"option_0000_imy":[(0,365,410,570),(670,280,960,390),(700,820,1024,1024)],
"sh_ui00_0000_imy":[(0,180,300,390),(780,190,990,620),(700,840,1024,1024)],
"system__fl_ui00_ptm":[(40,190,370,280),(440,190,770,380),(0,380,1024,946)],
"system__fl_ui01_ptm":[(0,350,490,470),(520,570,1015,680)],
"system__st_ui00_ptm":[(0,380,390,880)],
"system__st_ui01_ptm":[(0,110,165,190),(220,170,460,290),(55,335,235,525),(55,575,510,710),(25,850,335,945)],
"system__st_ui02_ptm":[(15,45,380,205),(400,50,750,205),(50,250,375,405),(430,250,745,405),(30,430,375,595),(50,650,350,790),(50,810,380,970),(590,770,900,900),(830,875,1024,1024)],
}
for i in range(5):
 B[f"punish_tutrial_{i}_imy"]=[(0,0,660,85),(1150,0,1885,85),(735,0,1125,115),(1425,90,1835,220),(120,205,1005,380),(100,430,615,505),(100,495,1020,655),(695,700,1425,1005)]
 B[f"punish_tutrial_dolce_{i}_imy"]=[(0,0,660,85),(1150,0,1885,85),(735,0,1125,115),(1425,90,1835,220),(120,205,1005,380),(100,430,615,505),(125,495,1305,705),(695,700,1425,1065)]
direct_report_path=ROOT/"ui_review/direct32_system_ko/report.json"
if direct_report_path.exists():
 direct_report=json.loads(direct_report_path.read_text(encoding="utf-8"))
 for item in direct_report.get("items",[]):
  B[item["label"]]=[tuple(box) for box in item["allowed_boxes"]]
rows=[];ok=True
for e in manifest:
 label=e["label"]; jp=np.array(Image.open(e["source_jp"]).convert("RGBA")); ko=np.array(Image.open(e["korean_preview"]).convert("RGBA"))
 diff=np.any(jp!=ko,axis=2); changed=int(diff.sum())
 allowed=np.zeros(diff.shape,bool)
 for x0,y0,x1,y1 in B.get(label,[]): allowed[y0:y1,x0:x1]=True
 outside=int((diff&~allowed).sum())
 if e["modified"]:
  passed=changed>0 and outside==0 and label in B
 else:
  passed=changed==0
 ok &= passed
 rows.append({"label":label,"modified":e["modified"],"changed_pixels":changed,"changed_outside_contract":outside,"pass":passed})
out={"pass":ok,"assets":len(rows),"modified":sum(x["modified"] for x in rows),"unchanged":sum(not x["modified"] for x in rows),"rows":rows}
path=ROOT/"ui_review/full_mockups/preservation_verification.json";path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:v for k,v in out.items() if k!="rows"},ensure_ascii=False,indent=2))
for x in rows:
 if not x["pass"]: print("FAIL",x)
raise SystemExit(0 if ok else 1)
