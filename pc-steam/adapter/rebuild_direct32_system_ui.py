from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(r'P:\AI\Codex\projects\criminal-girls-invite-only-ko')
SRC=ROOT/'ui_review/full_audit/decoded'
OUT=ROOT/'ui_review/direct32_system_ko'
ASSETS=OUT/'assets'; ASSETS.mkdir(parents=True,exist_ok=True)
SANS=Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf')
SERIF=Path(r'C:\Windows\Fonts\NotoSerifKR-VF.ttf')


def fnt(size:int,family='sans',weight=800):
    f=ImageFont.truetype(str(SANS if family=='sans' else SERIF),size)
    f.set_variation_by_axes([max(100,min(900,weight))])
    return f


def fitted(draw,text,box,start,minimum=12,stroke=0,family='sans',weight=800):
    x0,y0,x1,y1=box
    for size in range(start,minimum-1,-1):
        f=fnt(size,family,weight); b=draw.textbbox((0,0),text,font=f,stroke_width=stroke)
        if b[2]-b[0] <= x1-x0 and b[3]-b[1] <= y1-y0:return f
    return fnt(minimum,family,weight)


def draw_text(im,box,text,start,minimum=12,fill=(255,255,255,255),stroke=2,stroke_fill=(0,0,0,255),family='sans',weight=800,align='center'):
    d=ImageDraw.Draw(im);f=fitted(d,text,box,start,minimum,stroke,family,weight);b=d.textbbox((0,0),text,font=f,stroke_width=stroke)
    x0,y0,x1,y1=box
    x=x0+((x1-x0)-(b[2]-b[0]))/2-b[0] if align=='center' else x0-b[0]
    y=y0+((y1-y0)-(b[3]-b[1]))/2-b[1]
    d.text((x,y),text,font=f,fill=fill,stroke_width=stroke,stroke_fill=stroke_fill)


def clear_box(im,box,color=(0,0,0,0)):
    # Boxes use half-open coordinates everywhere else; PIL rectangle is inclusive.
    x0,y0,x1,y1=box
    ImageDraw.Draw(im).rectangle((x0,y0,x1-1,y1-1),fill=color)


def wipe_column(im,box,sample_x):
    x0,y0,x1,y1=box;a=np.array(im.convert('RGBA'));a[y0:y1,x0:x1]=a[y0:y1,sample_x:sample_x+1];im.paste(Image.fromarray(a,'RGBA'))


def erase_bright(im,box,threshold=135,dilate=3):
    x0,y0,x1,y1=box;a=np.array(im.convert('RGBA'));c=a[y0:y1,x0:x1].copy();rgb=c[:,:,:3]
    m=((rgb.min(axis=2)>=threshold)&(c[:,:,3]>=48)).astype(np.uint8)*255
    if dilate:m=cv2.dilate(m,np.ones((2*dilate+1,2*dilate+1),np.uint8),iterations=1)
    if m.any():
        for ch in range(4):c[:,:,ch]=cv2.inpaint(c[:,:,ch],m,3,cv2.INPAINT_TELEA)
        a[y0:y1,x0:x1]=c;im.paste(Image.fromarray(a,'RGBA'))


def erase_chain_letters(im):
    """Inpaint only the gold CHAIN glyph components, retaining the lightning art."""
    a=np.array(im.convert('RGBA')); x0,y0,x1,y1=(620,880,920,1024)
    crop=a[y0:y1,x0:x1].copy(); rgb=crop[:,:,:3]
    r=rgb[:,:,0].astype(np.int16); g=rgb[:,:,1].astype(np.int16); b=rgb[:,:,2].astype(np.int16)
    gold=((r>120)&(g>55)&(b<100)&((r-b)>70)).astype(np.uint8)*255
    count,labels,stats,_=cv2.connectedComponentsWithStats(gold,8)
    mask=np.zeros(gold.shape,np.uint8)
    for idx in range(1,count):
        x,y,w,h,area=map(int,stats[idx])
        if area>=80 and y<=70 and y+h>=55:
            mask[labels==idx]=255
    mask=cv2.dilate(mask,np.ones((9,9),np.uint8),iterations=1)
    for ch in range(4):
        crop[:,:,ch]=cv2.inpaint(crop[:,:,ch],mask,5,cv2.INPAINT_TELEA)
    a[y0:y1,x0:x1]=crop; im.paste(Image.fromarray(a,'RGBA'))


def erase_blue_diagonal(im):
    a=np.array(im.convert('RGBA'));rgb=a[:,:,:3];yy,xx=np.mgrid[0:a.shape[0],0:a.shape[1]]
    poly=np.array([[720,920],[790,1015],[1023,805],[1000,700]],np.int32)
    pm=np.zeros(a.shape[:2],np.uint8);cv2.fillConvexPoly(pm,poly,255)
    blue=(rgb[:,:,2].astype(np.int16)>rgb[:,:,0].astype(np.int16)+35)&(rgb[:,:,2]>=120)&(a[:,:,3]>=70)
    m=((pm>0)&blue).astype(np.uint8)*255;m=cv2.dilate(m,np.ones((7,7),np.uint8),iterations=1)
    for ch in range(4):a[:,:,ch]=cv2.inpaint(a[:,:,ch],m,3,cv2.INPAINT_TELEA)
    im.paste(Image.fromarray(a,'RGBA'))


def rotated(im,center,text,angle,start,box_size,fill=(255,255,255,255),stroke=2,stroke_fill=(0,0,0,255),family='sans',weight=850,minimum=18):
    w,h=box_size;tmp=Image.new('RGBA',(w,h),(0,0,0,0));draw_text(tmp,(0,0,w,h),text,start,minimum,fill,stroke,stroke_fill,family,weight)
    rr=tmp.rotate(angle,expand=True,resample=Image.Resampling.BICUBIC)
    im.alpha_composite(rr,(int(center[0]-rr.width/2),int(center[1]-rr.height/2)))


def load(label):return Image.open(SRC/f'{label}__jp.png').convert('RGBA')

def save(label,im,allowed):
    src=load(label);a=np.array(src);b=np.array(im);changed=np.any(a!=b,axis=2);ys,xs=np.where(changed)
    outside=changed.copy()
    for x0,y0,x1,y1 in allowed:outside[y0:y1,x0:x1]=False
    if outside.any():raise RuntimeError(f'{label}: {outside.sum()} changed pixels outside allowlist')
    p=ASSETS/f'{label}__ko.png';im.save(p,optimize=True)
    return {'label':label,'source':str(SRC/f'{label}__jp.png'),'output':str(p),'changed_pixels':int(changed.sum()),'changed_bbox':[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)] if len(xs) else None,'allowed_boxes':[list(x) for x in allowed],'outside_allowlist':int(outside.sum())}

reports=[]
# Field/map atlas.
label='system__fl_ui00_ptm';im=load(label);allowed=[]
for wipe,sample,box,text in [
 ((95,205,325,265),88,(48,195,365,276),'시스템'),
 ((505,205,715,265),490,(450,195,760,276),'파티'),
 ((500,300,720,365),480,(450,291,760,375),'메뉴')]:
    wipe_column(im,wipe,sample);draw_text(im,box,text,43,22,family='serif',weight=850);allowed.append((min(wipe[0],box[0]),min(wipe[1],box[1]),max(wipe[2],box[2]),max(wipe[3],box[3])))
for box,text in [
 ((0,385,505,460),'제832 감옥동'),((515,385,1024,460),'X층: 지배자의 구역'),
 ((0,475,505,555),'1층: 수렁'),((515,475,1024,555),'허공 좌표 437'),
 ((0,570,505,650),'2층: 불지옥'),((0,665,505,748),'3층: 얼음'),
 ((0,760,505,842),'교육동'),((0,855,505,940),'소녀 지옥')]:
    clear_box(im,box);draw_text(im,(box[0]+6,box[1],box[2]-6,box[3]),text,52,25,stroke=3,family='sans',weight=900,align='left');allowed.append(box)
reports.append(save(label,im,allowed))

label='system__fl_ui01_ptm';im=load(label);allowed=[]
for box in [(0,350,500,475),(515,565,1024,690)]:
    clear_box(im,box);draw_text(im,(box[0]+6,box[1],box[2]-6,box[3]),'옛 기억의 정원',58,30,stroke=3,family='sans',weight=900,align='left');allowed.append(box)
reports.append(save(label,im,allowed))

label='system__st_ui00_ptm';im=load(label);allowed=[]
# Straight labels.
for wipe,sample,box,text,size,family in [
 ((95,390,335,465),360,(80,380,350,470),'메뉴',48,'serif'),
 ((0,650,330,720),360,(0,645,330,722),'필드 스킬',43,'sans'),
 ((0,720,280,790),310,(0,716,300,794),'상태',43,'sans'),
 ((0,790,360,860),380,(0,785,370,865),'파티 아이템',42,'sans')]:
    wipe_column(im,wipe,sample);draw_text(im,box,text,size,18,stroke=2,family=family,weight=900,align='left' if text!='메뉴' else 'center');allowed.append((min(wipe[0],box[0]),min(wipe[1],box[1]),max(wipe[2],box[2]),max(wipe[3],box[3])))
# Angled labels; erase only their bright glyphs, preserving purple bands.
for ebox,center,text,size,angle in [
 ((490,470,700,590),(590,530),'뒤로',43,17),
 ((420,690,650,820),(535,755),'목록',43,17),
 ((690,850,975,1005),(835,925),'나가기',42,17)]:
    erase_bright(im,ebox,115,3);rotated(im,center,text,angle,size,(240,86),family='serif',weight=750);allowed.append(ebox)
reports.append(save(label,im,allowed))

label='system__st_ui01_ptm';im=load(label);allowed=[]
for wipe,sample,box,text,size in [
 ((5,120,135,180),155,(5,115,150,185),'레벨',33),
 ((225,175,440,232),455,(220,170,445,237),'경험치',32),
 ((225,228,440,282),455,(220,225,445,287),'다음',32),
 ((65,345,200,423),220,(65,342,205,425),'HP',40),
 ((65,440,200,513),220,(65,438,205,516),'MP',40),
 ((65,585,210,648),225,(60,580,220,652),'공격',31),
 ((310,585,495,648),295,(300,580,505,652),'마공',31),
 ((65,635,210,698),225,(60,630,220,702),'방어',31),
 ((310,635,500,698),295,(300,630,510,702),'마방',31),
 ((35,865,280,935),320,(30,855,300,945),'오더',40)]:
    wipe_column(im,wipe,sample);draw_text(im,box,text,size,15,stroke=2,family='sans',weight=850,align='left');allowed.append((min(wipe[0],box[0]),min(wipe[1],box[1]),max(wipe[2],box[2]),max(wipe[3],box[3])))
erase_blue_diagonal(im);rotated(im,(895,865),'걸즈 오더',47,45,(360,92),fill=(25,145,255,255),stroke=3,stroke_fill=(0,0,0,255),family='sans',weight=900,minimum=26);allowed.append((700,690,1024,1024))
reports.append(save(label,im,allowed))

label='system__st_ui02_ptm';im=load(label);allowed=[]
for box,center,text,size,angle in [
 ((20,45,360,210),(185,125),'키사라기',58,14),
 ((410,50,735,210),(575,130),'앨리스',58,14),
 ((55,255,355,410),(200,335),'유코',62,14),
 ((440,255,730,410),(590,335),'란',64,14),
 ((35,430,360,600),(195,515),'토모에',58,14),
 ((55,650,330,790),(190,720),'신',65,14),
 ((45,805,370,965),(205,885),'사코',62,14)]:
    clear_box(im,box);rotated(im,center,text,angle,size,(box[2]-box[0],box[3]-box[1]),family='sans',weight=900,minimum=28);allowed.append(box)
# MAX LV: keep the gold emblem and replace only white/yellow letters.
mbox=(790,255,1005,420);erase_bright(im,mbox,120,2);draw_text(im,(800,275,995,405),'최대 레벨',40,22,fill=(255,239,80,255),stroke=3,family='sans',weight=900);allowed.append(mbox)
# Attack plaque: restore its original solid magenta face, then replace only text.
pink=(212,15,155,255)
clear_box(im,(645,809,790,866),pink)
draw_text(im,(645,807,790,868),'공격',48,28,fill=(0,0,0,255),stroke=0,family='sans',weight=900)
allowed.append((639,805,855,869))

# CHAIN uses a lightning-backed display treatment. Remove the connected gold
# Latin glyph faces, retain the surrounding lightning, and typeset Korean in
# the same gold/black treatment.
erase_chain_letters(im)
rotated(im,(785,947),'체인!',12,58,(260,104),fill=(255,225,55,255),stroke=5,stroke_fill=(0,0,0,255),family='sans',weight=900,minimum=34)
allowed.append((620,880,920,1024))

# The bond name sits on a flat magenta plaque; restore that face exactly.
clear_box(im,(860,930,990,987),pink)
draw_text(im,(860,928,990,989),'유대',48,28,fill=(0,0,0,255),stroke=0,family='sans',weight=900)
allowed.append((747,925,993,990))
reports.append(save(label,im,allowed))

# Bind the corrected previews into the aggregate mockup manifest used by the encoder.
manifest_path=ROOT/'ui_review/full_mockups/manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
by={x['label']:x for x in reports}
for row in manifest:
    if row['label'] in by:
        row['korean_preview']=by[row['label']]['output'];row['status']='32-bit direct-color runtime-corrected';row['modified']=True
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report={'schema':'criminal-girls.direct32-system-ui.v1','status':'PASS','asset_count':len(reports),'items':reports,'manifest':str(manifest_path)}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','asset_count':len(reports),'changed_pixels':sum(x['changed_pixels'] for x in reports),'outside_allowlist':sum(x['outside_allowlist'] for x in reports)},ensure_ascii=False,indent=2))
