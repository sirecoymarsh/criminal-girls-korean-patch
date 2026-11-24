#!/usr/bin/env python3
"""Build every Korean raster-UI review candidate for the Japanese language slot."""
from __future__ import annotations
import json, math
import cv2, numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(r"P:\AI\Codex\projects\criminal-girls-invite-only-ko")
DECODED=ROOT/"ui_review/full_audit/decoded"
OUT=ROOT/"ui_review/full_mockups"; ASSETS=OUT/"assets"; SHEETS=OUT/"sheets"
FONT_SANS=Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf")
FONT_SERIF=Path(r"C:\Windows\Fonts\NotoSerifKR-VF.ttf")
ASSETS.mkdir(parents=True,exist_ok=True); SHEETS.mkdir(parents=True,exist_ok=True)

# Typography contract: use the Korean counterpart of the source family and
# lock weight explicitly.  The previous draft used the VF default (weight 100),
# which made every label much thinner than the source artwork.
def font(size,family="serif",weight=700):
    path=FONT_SERIF if family=="serif" else FONT_SANS
    f=ImageFont.truetype(str(path),size=size)
    f.set_variation_by_axes([max(200 if family=="serif" else 100,min(900,weight))])
    return f

def fit(draw,text,box,start,minimum=10,stroke=0,multi=False,spacing=4,family="serif",weight=700):
    x0,y0,x1,y1=box
    for size in range(start,minimum-1,-1):
        f=font(size,family,weight)
        b=draw.multiline_textbbox((0,0),text,font=f,spacing=spacing,stroke_width=stroke) if multi else draw.textbbox((0,0),text,font=f,stroke_width=stroke)
        if b[2]-b[0]<=x1-x0 and b[3]-b[1]<=y1-y0:return f
    return font(minimum,family,weight)

def centered(draw,box,text,fill=(254,254,254,255),start=40,minimum=10,sw=1,sf=(0,0,0,255),family="serif",weight=700):
    f=fit(draw,text,box,start,minimum,sw,False,4,family,weight); x0,y0,x1,y1=box
    b=draw.textbbox((0,0),text,font=f,stroke_width=sw)
    draw.text((x0+((x1-x0)-(b[2]-b[0]))/2-b[0],y0+((y1-y0)-(b[3]-b[1]))/2-b[1]),text,font=f,fill=fill,stroke_width=sw,stroke_fill=sf)

def ccenter(im,box,text,start=40,fill=(254,254,254,255),bg=(3,2,6,255),sw=1,sf=(0,0,0,255),minimum=10,family="serif",weight=700):
    erase_bright_text(im,box,105,1)
    centered(ImageDraw.Draw(im),box,text,fill,start,minimum,sw,sf,family,weight)

def cleft(im,box,text,start=34,fill=(254,254,254,255),bg=(0,0,0,0),sw=1,sf=(0,0,0,255),minimum=9,pad=4,family="serif",weight=700):
    if bg[3]: ImageDraw.Draw(im).rectangle(box,fill=bg)
    else: erase_bright_text(im,box,105,1)
    d=ImageDraw.Draw(im);f=fit(d,text,(box[0]+pad,box[1],box[2]-pad,box[3]),start,minimum,sw,False,4,family,weight)
    b=d.textbbox((0,0),text,font=f,stroke_width=sw);y=box[1]+((box[3]-box[1])-(b[3]-b[1]))/2-b[1]
    d.text((box[0]+pad,y),text,font=f,fill=fill,stroke_width=sw,stroke_fill=sf)

def decoded(label,lang="jp"):return Image.open(DECODED/f"{label}__{lang}.png").convert("RGBA")
def save(label,im):
    p=ASSETS/f"{label}__ko.png";im.save(p,optimize=True);return p
def panel(d,box,title,body):
    x0,y0,x1,y1=box;d.rounded_rectangle(box,radius=10,fill=(4,3,7,255))
    tf=fit(d,title,(x0+4,y0+3,x1-4,y0+48),31,18,1,family="serif",weight=700);d.text((x0+5,y0+3),title,font=tf,fill=(246,216,124,255),stroke_width=1,stroke_fill=(50,30,5,255))
    bb=(x0+25,y0+50,x1-10,y1-9);bf=fit(d,body,bb,30,21,1,True,6,"serif",600)
    d.multiline_text((bb[0],bb[1]),body,font=bf,fill=(250,250,250,255),spacing=6,stroke_width=1,stroke_fill=(0,0,0,255))

COMMON_INTRO="소녀들의 나쁜 마음이 적이 되어 나타납니다.\n제한 시간 안에 쓰러뜨려\n소녀들을 갱생시키세요!"
COMMON_COLOR="적은 빨강과 파랑, 두 종류로 나타납니다.\n빨간 적은 왼쪽 클릭,\n파란 적은 오른쪽 클릭으로\n공략하세요."
TUT=[
("스팽킹 벌주기","채찍으로 적을 때려 쓰러뜨려라!",
 "마우스를 클릭하면 채찍이 나타납니다.\n채찍으로 적을 연속해서 때려 쓰러뜨리세요.",
 "방향 버튼으로 커서를 움직인 뒤 버튼을 눌러 채찍을 꺼내세요.\n버튼을 연속해서 눌러 적을 쓰러뜨리세요."),
("미끈미끈 조교 벌주기","적에게 액체를 떨어뜨려 쓰러뜨려라!",
 "마우스를 누르고 있으면 병이 나타납니다.\n병에서 액체를 떨어뜨려 적을 쓰러뜨리세요.",
 "방향 버튼으로 커서를 움직이고 버튼을 눌러 병을 꺼내세요.\n병의 액체를 적에게 떨어뜨려 쓰러뜨리세요."),
("간질간질 지도 벌주기","깃털 먼지털이로 적을 간질여라!",
 "마우스를 누르고 있으면 깃털 먼지털이가 나타납니다.\n적을 간질여 쓰러뜨리세요.",
 "방향 버튼으로 커서를 움직이고 버튼을 눌러 먼지털이를 꺼내세요.\n적을 간질여 쓰러뜨리세요."),
("전기 찌릿 벌주기","적의 등 스위치를 움직여라!",
 "적의 스위치를 클릭한 채 끌어내려\n적을 쓰러뜨리세요.",
 "방향 버튼으로 커서를 움직인 뒤 스위치에서 버튼을 누르세요.\n버튼을 누른 채 경로를 따라 움직여 적을 쓰러뜨리세요."),
("치유 주물주물","적을 잡아 같은 색의 원까지 옮겨라!",
 "마우스로 적을 잡아 같은 색의 원까지 옮긴 뒤\n놓으면 적을 쓰러뜨릴 수 있습니다.",
 "방향 버튼으로 커서를 움직이고 버튼을 눌러 적을 잡으세요.\n같은 색의 원까지 옮긴 뒤 버튼을 놓으세요.")]

def erase_bright_text(im,box,threshold=150,dilate=2):
    """Remove bright glyph strokes only; preserve the underlying decorated bar."""
    x0,y0,x1,y1=box
    rgba=np.array(im.convert("RGBA")); crop=rgba[y0:y1,x0:x1]
    rgb=crop[:,:,:3]
    # Japanese headers in these bars are neutral/light strokes. Requiring all
    # channels to be bright avoids the gold/purple ornament around them.
    mask=((rgb.min(axis=2)>=threshold)&(crop[:,:,3]>=64)).astype(np.uint8)*255
    if dilate:
        mask=cv2.dilate(mask,np.ones((dilate*2+1,dilate*2+1),np.uint8),iterations=1)
    if mask.any():
        for channel in range(4):
            crop[:,:,channel]=cv2.inpaint(crop[:,:,channel],mask,3,cv2.INPAINT_TELEA)
        rgba[y0:y1,x0:x1]=crop
        im.paste(Image.fromarray(rgba,"RGBA"))


def erase_warm_text(im,box,dilate=1):
    """Inpaint bright orange/gold label faces while retaining darker artwork."""
    x0,y0,x1,y1=box
    rgba=np.array(im.convert("RGBA")); crop=rgba[y0:y1,x0:x1].copy()
    rgb=crop[:,:,:3]
    mask=((rgb[:,:,0]>=110)&(rgb[:,:,1]>=55)&(rgb[:,:,2]<=115)&
          ((rgb[:,:,0].astype(np.int16)-rgb[:,:,2].astype(np.int16))>=48)&
          (crop[:,:,3]>=80)).astype(np.uint8)*255
    if dilate:
        mask=cv2.dilate(mask,np.ones((dilate*2+1,dilate*2+1),np.uint8),iterations=1)
    if mask.any():
        for channel in range(4):
            crop[:,:,channel]=cv2.inpaint(crop[:,:,channel],mask,3,cv2.INPAINT_TELEA)
        rgba[y0:y1,x0:x1]=crop; im.paste(Image.fromarray(rgba,"RGBA"))


def clean_black_panel(im,box):
    """Restore only the enclosed black interior of an ornate tutorial panel."""
    x0,y0,x1,y1=box
    rgba=np.array(im.convert("RGBA")); crop=rgba[y0:y1,x0:x1].copy()
    rgb=crop[:,:,:3]
    dark=((rgb.max(axis=2)<=62)&(crop[:,:,3]>=100)).astype(np.uint8)*255
    dark=cv2.morphologyEx(dark,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8),iterations=1)
    contours,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError(f"tutorial panel interior not found: {box}")
    contour=max(contours,key=cv2.contourArea)
    if cv2.contourArea(contour)<0.2*(x1-x0)*(y1-y0):
        raise RuntimeError(f"tutorial panel interior too small: {box}")
    mask=np.zeros(dark.shape,np.uint8); cv2.drawContours(mask,[contour],-1,255,thickness=cv2.FILLED)
    crop[mask>0]=np.array((4,3,7,255),dtype=np.uint8)
    rgba[y0:y1,x0:x1]=crop; im.paste(Image.fromarray(rgba,"RGBA"))


def wipe_with_column(im,box,sample_x):
    """Remove a label while retaining the button's vertical texture/alpha profile."""
    x0,y0,x1,y1=box
    rgba=np.array(im.convert("RGBA"))
    rgba[y0:y1,x0:x1]=rgba[y0:y1,sample_x:sample_x+1]
    im.paste(Image.fromarray(rgba,"RGBA"))


def erase_contrast_text(im,box,threshold=20,dilate=2):
    """Inpaint high-frequency glyph strokes inside a tightly bounded label area."""
    x0,y0,x1,y1=box
    rgba=np.array(im.convert("RGBA")); crop=rgba[y0:y1,x0:x1].copy()
    rgb=crop[:,:,:3]
    blur=cv2.medianBlur(rgb,11)
    diff=np.max(np.abs(rgb.astype(np.int16)-blur.astype(np.int16)),axis=2)
    mask=((diff>=threshold)&(crop[:,:,3]>=16)).astype(np.uint8)*255
    mask=cv2.dilate(mask,np.ones((dilate*2+1,dilate*2+1),np.uint8),iterations=1)
    if mask.any():
        for channel in range(4):crop[:,:,channel]=cv2.inpaint(crop[:,:,channel],mask,3,cv2.INPAINT_TELEA)
        rgba[y0:y1,x0:x1]=crop;im.paste(Image.fromarray(rgba,"RGBA"))


def erase_blue_ink(im,box,dilate=2):
    """Remove the cyan/blue Japanese location glyphs from the RGBA4444 atlas."""
    x0,y0,x1,y1=box
    rgba=np.array(im.convert("RGBA")); crop=rgba[y0:y1,x0:x1].copy()
    mask=((crop[:,:,2]>=170)&(crop[:,:,3]>=180)).astype(np.uint8)*255
    mask=cv2.dilate(mask,np.ones((dilate*2+1,dilate*2+1),np.uint8),iterations=1)
    if mask.any():
        for channel in range(4):crop[:,:,channel]=cv2.inpaint(crop[:,:,channel],mask,3,cv2.INPAINT_TELEA)
        rgba[y0:y1,x0:x1]=crop;im.paste(Image.fromarray(rgba,"RGBA"))


def draw_left(im,box,text,start=34,fill=(245,245,245,255),sw=1,sf=(15,0,25,255),minimum=12,pad=4,family="serif",weight=700):
    d=ImageDraw.Draw(im);f=fit(d,text,(box[0]+pad,box[1],box[2]-pad,box[3]),start,minimum,sw,False,4,family,weight)
    b=d.textbbox((0,0),text,font=f,stroke_width=sw);y=box[1]+((box[3]-box[1])-(b[3]-b[1]))/2-b[1]
    d.text((box[0]+pad,y),text,font=f,fill=fill,stroke_width=sw,stroke_fill=sf)


def slanted_text(im,box,text,start=52,fill=(255,255,255,255),sw=2,sf=(0,0,0,255),minimum=18,family="sans",weight=900,shear=0.16):
    """Render a heavy display label with the source artwork's forward slant."""
    x0,y0,x1,y1=box; w=x1-x0; h=y1-y0; extra=max(8,int(h*abs(shear))+4)
    tmp=Image.new("RGBA",(w+extra,h),(0,0,0,0)); td=ImageDraw.Draw(tmp)
    centered(td,(0,0,w,h),text,fill,start,minimum,sw,sf,family,weight)
    warped=tmp.transform(tmp.size,Image.Transform.AFFINE,(1,shear,-shear*h,0,1,0),resample=Image.Resampling.BICUBIC)
    im.alpha_composite(warped,(x0,y0))


def tutorial_text(d,title_box,body_box,title,body,title_color,body_size=39):
    tf=fit(d,title,title_box,40,26,1,False,4,"serif",700)
    tb=d.textbbox((0,0),title,font=tf,stroke_width=1)
    ty=title_box[1]+((title_box[3]-title_box[1])-(tb[3]-tb[1]))/2-tb[1]
    d.text((title_box[0],ty),title,font=tf,fill=title_color,stroke_width=1,stroke_fill=(35,0,38,255))
    bf=fit(d,body,body_box,body_size,27,1,True,8,"serif",650)
    d.multiline_text((body_box[0],body_box[1]),body,font=bf,fill=(253,253,253,255),spacing=8,stroke_width=1,stroke_fill=(0,0,0,255))


def clear_text_area(im,box,color=(4,3,7,255)):
    """Clear a measured source-text rectangle inside an already-black panel."""
    ImageDraw.Draw(im).rectangle(box,fill=color)


def draw_counter(im,box):
    d=ImageDraw.Draw(im); parts=[("남은",30,700,(255,255,255,255)),("02",47,800,(255,146,226,255)),("회",30,700,(255,255,255,255))]
    measured=[]; total=0
    for t,sz,w,c in parts:
        f=font(sz,"serif",w); b=d.textbbox((0,0),t,font=f,stroke_width=1); width=b[2]-b[0]
        measured.append((t,f,b,width,c)); total+=width
    gaps=10; total+=gaps*(len(parts)-1); x=box[0]+((box[2]-box[0])-total)/2
    for t,f,b,width,c in measured:
        y=box[1]+((box[3]-box[1])-(b[3]-b[1]))/2-b[1]
        d.text((x-b[0],y),t,font=f,fill=c,stroke_width=1,stroke_fill=(0,0,0,255)); x+=width+gaps


def build_tutorial(label,info):
    title,obj,method_mouse,method_dolce=info; im=decoded(label)
    dolce="_dolce_" in label; method=method_dolce if dolce else method_mouse

    # Header bars: erase only source glyph strokes; keep roses, borders and gradients.
    erase_bright_text(im,(5,5,655,82),150,2)
    erase_bright_text(im,(1160,5,1880,82),150,2)
    d=ImageDraw.Draw(im)
    centered(d,(12,7,640,78),title,(255,244,255,255),38,24,1,(40,0,50,255),"serif",700)
    centered(d,(1170,7,1875,78),obj,(255,246,255,255),36,22,1,(45,0,55,255),"serif",700)

    # Opaque caption plaques contain no decorative art inside their dark face.
    clean_black_panel(im,(735,0,1125,115)); draw_counter(im,(765,8,1100,103))
    clean_black_panel(im,(1425,90,1835,220)); d=ImageDraw.Draw(im)
    centered(d,(1460,118,1795,198),"조작 설명",(255,255,255,255),40,26,1,(0,0,0,255),"serif",700)

    # Measured text-only regions. Circled numerals, curls, roses and frames stay original.
    clear_text_area(im,(125,210,995,370)); d=ImageDraw.Draw(im)
    intro_box=(139,225,965,365)
    f=fit(d,COMMON_INTRO,intro_box,40,31,1,True,8,"serif",650)
    d.multiline_text((intro_box[0],intro_box[1]),COMMON_INTRO,font=f,fill=(253,253,253,255),spacing=8,stroke_width=1,stroke_fill=(0,0,0,255))

    pink=(250,142,231,255); cyan=(100,235,245,255)
    if dolce:
        clear_text_area(im,(105,435,570,500)); clear_text_area(im,(130,500,1300,700))
        # Full measured Japanese title/body bands; prior y-start left visible glyphs.
        clear_text_area(im,(715,700,1420,1060))
        d=ImageDraw.Draw(im)
        tutorial_text(d,(120,440,610,500),(182,528,1290,700),"적을 쓰러뜨리는 법",method,pink,38)
        tutorial_text(d,(740,705,1205,790),(740,800,1400,1035),"색이 다른 적",COMMON_COLOR,cyan,38)
    else:
        clear_text_area(im,(105,435,570,500)); clear_text_area(im,(105,500,1015,650))
        clear_text_area(im,(715,700,1420,1000))
        d=ImageDraw.Draw(im)
        tutorial_text(d,(120,440,610,500),(118,511,1005,650),"적을 쓰러뜨리는 법",method,pink,39)
        tutorial_text(d,(740,705,1205,790),(740,800,1400,975),"색이 다른 적",COMMON_COLOR,cyan,38)
    return im

res=[];mod=set()
def done(label,im,status="한국어화"):
    mod.add(label);res.append((label,save(label,im),status))

label="bt_ui_00_0000_imy";im=decoded(label);d=ImageDraw.Draw(im)
for inner in [(10,524,360,594),(396,524,745,594),(10,620,360,691)]:d.rectangle(inner,fill=(1,1,3,255))
for b,t in [((0,516,370,602),"교대"),((386,516,755,602),"아이템"),((0,612,370,699),"도주")]:ccenter(im,b,t,56,bg=(1,1,3,255),family="serif",weight=800)
d.rectangle((0,350,220,450),fill=(0,0,0,0));d.rectangle((225,390,510,510),fill=(0,0,0,0))
slanted_text(im,(0,350,285,500),"연계!",72,(177,255,40,255),4,(30,75,0,255),34,"sans",900)
slanted_text(im,(225,395,505,510),"치명타!",66,(255,190,35,255),4,(95,30,0,255),30,"sans",900);done(label,im)

label="bt_ui_01_0000_imy";im=decoded(label);d=ImageDraw.Draw(im)
for inner in [(8,650,268,710),(298,650,554,710),(8,940,363,1010)]:d.rectangle(inner,fill=(1,1,3,255))
for b,t,s in [((0,642,276,718),"확인",50),((290,642,562,718),"뒤로",50),((0,932,371,1018),"교대",54)]:ccenter(im,b,t,s,bg=(1,1,3,255),family="serif",weight=800)
done(label,im)

for label in ["bt_ui_02_0000_imy","bt_ui_07_0001_imy"]:
    im=decoded(label);d=ImageDraw.Draw(im);d.rectangle((10,203,267,267),fill=(1,1,3,255));d.rectangle((10,302,267,366),fill=(1,1,3,255));ccenter(im,(0,194,277,276),"확인",50,bg=(1,1,3,255),family="serif",weight=800);ccenter(im,(0,293,277,374),"뒤로",50,bg=(1,1,3,255),family="serif",weight=800);done(label,im)

label="bt_ui_07_0000_imy";im=decoded(label)
erase_bright_text(im,(0,42,78,108),100,1);draw_left(im,(0,50,130,105),"레벨",40,sw=2,family="sans",weight=800)
erase_warm_text(im,(45,100,255,190),2);slanted_text(im,(20,108,300,220),"레벨 업!",58,(255,190,40,255),3,(95,35,0,255),30,"sans",900)
d=ImageDraw.Draw(im);d.rectangle((185,238,510,305),fill=(0,0,0,0));d.rectangle((185,304,510,375),fill=(0,0,0,0))
draw_left(im,(188,245,500,305),"경험치",43,(255,247,183,255),family="serif",weight=700);draw_left(im,(188,310,500,370),"합계",43,(255,247,183,255),family="serif",weight=700);ImageDraw.Draw(im).rectangle((8,428,310,488),fill=(1,1,3,255));ccenter(im,(0,420,318,495),"아이템 획득",46,bg=(1,1,3,255),family="serif",weight=800);done(label,im)

label="fl_ui03_imy";im=decoded(label)
for i,t in enumerate(["위층","아래층","문","스위치","보물","캠프","통로","현재 위치"]):cleft(im,(205,i*64,440,i*64+58),t,48,bg=(0,0,0,0),minimum=26,family="serif",weight=700)
d=ImageDraw.Draw(im)
for inner in [(153,524,412,582),(494,428,767,492),(494,524,767,582)]:d.rectangle(inner,fill=(1,1,3,255))
for b,t in [((145,516,420,590),"도움말"),((486,420,775,500),"닫기"),((486,516,775,590),"뒤로")]:ccenter(im,b,t,50,bg=(1,1,3,255),family="serif",weight=800)
done(label,im)

for label,items in [
("ic000_001_0000_00_imy",[((95,10,255,72),(18,5,282,84),"조사")]),
("ic000_002_0000_00_imy",[((95,10,255,72),(18,5,282,84),"대화")]),
("ic000_003_0000_00_imy",[((90,2,270,64),(18,0,300,72),"포털"),((285,55,485,122),(225,50,510,126),"캠프")])]:
    im=decoded(label)
    for erase_box,draw_box,t in items:
        erase_bright_text(im,erase_box,100,1);centered(ImageDraw.Draw(im),draw_box,t,start=52,minimum=28,sw=1,sf=(20,0,30,255),family="sans",weight=800)
    done(label,im)

label="option_0000_imy";im=decoded(label);d=ImageDraw.Draw(im)
for b,t in [((0,377,400,430),"BGM 음량"),((0,440,400,493),"효과음 음량"),((0,503,400,558),"음성 음량")]:cleft(im,b,t,49,bg=(0,0,0,0),sw=2,minimum=28,family="sans",weight=800)
ImageDraw.Draw(im).rectangle((688,300,940,368),fill=(1,1,3,255));ccenter(im,(678,290,950,378),"테스트",50,bg=(1,1,3,255),family="serif",weight=800);erase_bright_text(im,(760,865,930,995),100,1)
tmp=Image.new("RGBA",(240,70),(0,0,0,0));centered(ImageDraw.Draw(tmp),(0,0,240,70),"나가기",start=48,minimum=28,sw=2,sf=(0,0,0,255),family="serif",weight=800);im.alpha_composite(tmp.rotate(20,expand=True,resample=Image.Resampling.BICUBIC),(735,850));done(label,im)

label="sh_ui00_0000_imy";im=decoded(label);d=ImageDraw.Draw(im);d.rectangle((13,203,267,268),fill=(1,1,3,255));d.rectangle((13,302,267,364),fill=(1,1,3,255))
for clear in [(800,200,940,280),(800,275,940,345),(800,345,940,400),(800,405,940,465),(795,465,940,532),(800,530,940,610)]:d.rectangle(clear,fill=(0,0,0,0))
for b,t,s in [((5,195,275,276),"확인",42),((5,294,275,372),"뒤로",42),((800,205,960,278),"구매",43),((800,275,970,345),"판매",43),((800,347,948,398),"구매",31),((800,410,948,463),"판매",31),((795,470,965,530),"보유",32),((800,535,965,603),"신규",40)]:ccenter(im,b,t,s,bg=(1,1,3,255),family="serif" if t in {"확인","뒤로"} else "sans",weight=800 if t in {"확인","뒤로"} else 900)
erase_bright_text(im,(760,880,940,1000),100,1);tmp=Image.new("RGBA",(230,70),(0,0,0,0));centered(ImageDraw.Draw(tmp),(0,0,230,70),"나가기",start=48,minimum=28,sw=2,sf=(0,0,0,255),family="serif",weight=800);im.alpha_composite(tmp.rotate(20,expand=True,resample=Image.Resampling.BICUBIC),(735,870));done(label,im)

for prefix in ["punish_tutrial","punish_tutrial_dolce"]:
    for i,info in enumerate(TUT):
        label=f"{prefix}_{i}_imy";done(label,build_tutorial(label,info))

label="system__fl_ui00_ptm";im=decoded(label)
# Preserve the original button frames and color bands. Only the central English
# label area is replaced using a clean vertical profile from the same button.
for wipe,sample,drawbox,t,size in [
    ((95,205,325,265),88,(48,195,365,276),"시스템",42),
    ((505,205,715,265),490,(450,195,760,276),"파티",42),
    ((500,300,720,365),480,(450,291,760,375),"메뉴",42)]:
    wipe_with_column(im,wipe,sample);centered(ImageDraw.Draw(im),drawbox,t,(255,255,255,255),size,20,1,(20,0,25,255),"serif",800)
# The source location names use cyan faces and green shadows over a nearly
# transparent brown atlas matte. Restore that matte first, then typeset Korean
# in the same cyan/green treatment.
ImageDraw.Draw(im).rectangle((0,380,1024,945),fill=(153,85,17,0))
for b,t in [((5,390,500,452),"수감동 지하 2층"),((520,390,1015,452),"X층: 지배자의 영역"),((5,482,500,548),"1층: 진흙의 시련"),((520,482,1015,548),"허공 좌표 437"),((5,580,500,643),"2층: 불꽃의 시련"),((5,675,500,740),"3층: 얼음의 시련"),((5,770,500,835),"배움터"),((5,865,500,930),"소녀 지옥")]:
    draw_left(im,b,t,48,fill=(51,255,255,255),sw=3,sf=(85,221,85,187),minimum=24,family="sans",weight=900)
done(label,im)

label="system__fl_ui01_ptm";im=decoded(label)
# Preserve the lightning emblem above the first name. Only the measured source
# glyph bands are transparent; the previous broad wipe removed original art.
d=ImageDraw.Draw(im);d.rectangle((0,350,490,470),fill=(0,0,0,0));d.rectangle((520,570,1015,680),fill=(0,0,0,0))
for b in [(0,350,490,470),(520,570,1015,680)]:
    draw_left(im,b,"옛 기억의 정원",56,fill=(195,190,210,190),sw=2,sf=(80,35,115,220),minimum=30,family="serif",weight=500)
done(label,im)

label="system__st_ui00_ptm";im=decoded(label)
for wipe,sample,drawbox,t,size in [
    ((95,390,335,465),360,(105,390,330,458),"메뉴",46),
    ((0,650,330,720),360,(0,650,310,720),"필드 스킬",44),
    ((0,720,280,790),310,(0,720,260,790),"상태",44),
    ((0,790,360,860),380,(0,790,350,860),"파티 아이템",42)]:
    wipe_with_column(im,wipe,sample);draw_left(im,drawbox,t,size,sw=2,minimum=18,family="serif",weight=700)
done(label,im)

label="system__st_ui01_ptm";im=decoded(label)
for wipe,sample,drawbox,t,size in [
    ((5,120,135,180),155,(5,120,135,180),"레벨",35),
    ((225,175,440,232),455,(230,180,430,232),"경험치",34),
    ((225,228,440,282),455,(230,230,430,280),"다음",34),
    ((65,345,200,423),220,(70,350,190,420),"HP",40),
    ((65,440,200,513),220,(70,445,190,510),"MP",40),
    ((65,585,210,648),225,(70,590,200,645),"공격",31),
    ((310,585,495,648),295,(320,590,475,645),"마공",31),
    ((65,635,210,698),225,(70,640,200,695),"방어",31),
    ((310,635,500,698),295,(320,640,490,695),"마방",31),
    ((35,865,280,935),320,(40,870,260,930),"순서",38)]:
    wipe_with_column(im,wipe,sample);draw_left(im,drawbox,t,size,sw=2,minimum=16,family="serif",weight=650)
done(label,im)

label="system__st_ui02_ptm";im=decoded(label)
for wipe,sample,drawbox,t,size in [
    ((25,55,340,195),365,(25,55,330,190),"키사라기",52),
    ((420,65,720,195),730,(425,75,715,190),"앨리스",52),
    ((70,270,340,390),360,(80,275,330,385),"유코",56),
    ((455,270,710,390),725,(465,275,700,385),"란",60),
    ((45,445,340,580),355,(55,455,330,570),"토모에",54),
    ((65,825,345,950),365,(70,835,335,940),"사코",56),
    ((70,670,300,770),330,(80,680,290,760),"죄",48),
    ((620,785,875,885),600,(630,790,865,875),"공격",45),
    ((860,890,1024,1000),840,(870,900,1020,990),"유대",42)]:
    wipe_with_column(im,wipe,sample);draw_left(im,drawbox,t,size,sw=3,minimum=20,family="serif",weight=700)
done(label,im)

all_labels=sorted({p.name[:-8] for p in DECODED.glob("*__jp.png")})
for label in all_labels:
    if label not in mod:res.append((label,save(label,decoded(label)),"문자 없음 · 일본어 원본 유지"))
res.sort(key=lambda x:x[0])
manifest=[{"label":l,"source_jp":str(DECODED/f"{l}__jp.png"),"korean_preview":str(p),"status":s,"modified":l in mod} for l,p,s in res]
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

lf=font(18,"sans",600);sf=font(17,"sans",600)
for old in SHEETS.glob("ui_ko_review_*.jpg"):old.unlink()
for page,start in enumerate(range(0,len(res),4),1):
    subset=res[start:start+4];cw=850;rh=470;sheet=Image.new("RGB",(cw*2,rh*len(subset)),(25,25,29));d=ImageDraw.Draw(sheet)
    for row,(label,kp,status) in enumerate(subset):
        for col,(tag,im) in enumerate([("일본어 원본",decoded(label)),("한국어 완성안",Image.open(kp).convert("RGBA"))]):
            bg=Image.new("RGBA",im.size,(18,18,22,255));bg.alpha_composite(im);bg.thumbnail((cw-24,rh-75),Image.Resampling.LANCZOS)
            x=col*cw+(cw-bg.width)//2;y=row*rh+62+(rh-68-bg.height)//2;sheet.paste(bg.convert("RGB"),(x,y));d.text((col*cw+12,row*rh+8),f"{label} · {tag}",font=lf,fill=(245,245,248))
        d.text((cw+12,row*rh+34),status,font=sf,fill=(130,255,180) if label in mod else (190,190,195))
    sheet.save(SHEETS/f"ui_ko_review_{page:02d}.jpg",quality=90,optimize=True)
summary={"audited_assets":len(res),"koreanized_assets":len(mod),"no_text_preserved_assets":len(res)-len(mod),"review_sheet_pages":math.ceil(len(res)/4),"output":str(OUT)}
(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps(summary,ensure_ascii=False,indent=2))
