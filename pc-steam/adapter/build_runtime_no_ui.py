import os,json,sys
from pathlib import Path
R=Path(os.environ['ROOT']);sys.path.insert(0,str(R/'adapter'))
from archive_repack import repack
m=json.loads(Path(os.environ['MAN']).read_text(encoding='utf-8'))
rows=[x for x in m['replacements'] if not (x['expected_name'].endswith('.imy') or x['expected_name'].endswith('.imy.bak'))]
n=dict(m);n['schema']='criminal-girls.runtime-isolation.no-ui';n['replacements']=rows;n['replacement_count']=len(rows);n['runtime_isolation_note']='all 72 image UI main/bak replacements removed; text/container replacements retained'
Path(os.environ['FILTERED']).write_text(json.dumps(n,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
r=repack(Path(m['source']),Path(os.environ['OUT']),'ps3fs',Path(os.environ['FILTERED']))
report=R/'audit/runtime_isolation_no_ui_build.json';report.write_text(json.dumps({'status':'PASS','replacement_count':len(rows),'excluded_count':len(m['replacements'])-len(rows),'output':os.environ['OUT'],'repack':r},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'replacement_count':len(rows),'excluded':len(m['replacements'])-len(rows),'output':os.environ['OUT']},indent=2))
