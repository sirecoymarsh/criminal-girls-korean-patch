import sys, os, struct, collections, tempfile, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'P:\AI\Codex\projects\criminal-girls-invite-only-ko\adapter')
from pathlib import Path
import archive_repack as A

ORIG = Path(r'P:\AI\Codex\projects\criminal-girls-invite-only-ko\install_backups\voicefix_20260901_live\CriminalGirlsInviteOnly-KoreanPatch-v2\backups\20260901_100010_a8b5e705c0394341b461b23615fe86b6\data_jp.dat')
KO = Path(r'P:\AI\Codex\projects\criminal-girls-invite-only-ko\release\korean_patch_jp_voicefix_20260901\payload\data_jp.dat')
OUT = Path(sys.argv[1]); dump = '--dump' in sys.argv
TEXTY = {'.bscr', '.bin', '.txt', '.dat', '.tbl', '.csv'}

def entries(p, fmt):
    return A.parse_template(p, fmt)[0]

def read(p, e):
    with open(p, 'rb') as f:
        f.seek(e.offset); return f.read(e.size)

def inner(data):
    if data[:8] != A.DS_MAGIC: return None
    t = tempfile.NamedTemporaryFile(delete=False); t.write(data); t.close()
    try:
        es = entries(Path(t.name), 'ds')
        return {e.name: data[e.offset:e.offset + e.size] for e in es}
    except Exception as ex:
        return None
    finally:
        os.unlink(t.name)

oe = {e.name: e for e in entries(ORIG, 'ps3fs')}
cnt = collections.Counter(); rep = []
for e in entries(KO, 'ps3fs'):
    o = oe.get(e.name)
    kd = read(KO, e)
    od = read(ORIG, o) if o else None
    if kd == od: continue
    ki = inner(kd)
    if ki is not None:
        oi = inner(od) if od else {}
        oi = oi or {}
        for n, d in ki.items():
            if oi.get(n) == d: continue
            ext = os.path.splitext(n)[1].lower(); cnt['inner' + ext] += 1
            rep.append((e.name, n, len(d)))
            if dump and ext in ('.imy', '.ptm'):
                p = OUT / e.name / n; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(d)
    else:
        ext = os.path.splitext(e.name)[1].lower(); cnt['outer' + ext] += 1
        rep.append((e.name, None, len(kd)))
        if dump and ext in ('.imy', '.ptm'):
            p = OUT / e.name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(kd)
print(cnt)
if dump:
    json.dump(rep, open(OUT / 'changed_entries.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
