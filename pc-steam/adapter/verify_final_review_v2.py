#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

def h(path: Path) -> str:
    x=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): x.update(b)
    return x.hexdigest()

def load(path: Path): return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args()
    root=a.root.resolve();pkg=root/'release/final_integrated_review_jp_v2'
    manifest=load(pkg/'package_sha256_manifest.json');expected={x['path']:x for x in manifest['files']}
    actual={p.relative_to(pkg).as_posix():p for p in pkg.rglob('*') if p.is_file() and p.name!='package_sha256_manifest.json'}
    hash_ok=all(name in actual and actual[name].stat().st_size==item['size'] and h(actual[name])==item['sha256'] for name,item in expected.items())
    main_html=(pkg/'FINAL_REVIEW.html').read_text(encoding='utf-8');scenario=(pkg/'translation/SCENARIO_REVIEW.html').read_text(encoding='utf-8');installer=(pkg/'INSTALLER_REVIEW.html').read_text(encoding='utf-8')
    summary=load(pkg/'package_summary.json');verification=load(pkg/'reports/review_package_verification.json');source_reports=root/'release/reports'
    names=['installer_package_build.json','installer_package_self_verification.json','installer_builder_fixture.json','installer_full_fixture.json','installer_fixture_matrix.json','defender_scan_korean_patch_jp_final_v1.json','installer_release_qa.json']
    reports_exact=all(h(pkg/'reports'/n)==h(source_reports/n) for n in names) and h(pkg/'reports/installer_manifest.json')==h(root/'release/korean_patch_jp_final_v1/manifest.json')
    links=['ui_review/UI_REVIEW.html','translation/SCENARIO_REVIEW.html','INSTALLER_REVIEW.html']
    checks={
      'manifest_exact_set':set(expected)==set(actual),'manifest_hashes':hash_ok,
      'package_summary_pass':summary.get('status')=='PASS' and summary.get('package_file_count')==len(actual)+1,
      'verification_pass':verification.get('status')=='PASS' and all(verification.get('checks',{}).values()),
      'three_review_links':all(f'href="{x}"' in main_html and (pkg/x).is_file() for x in links),
      'scenario_rows':len(re.findall(r'<tr class="(?:changed)?" data-status=',scenario))==2709,
      'scenario_header':scenario.startswith('<!doctype html>') and '<html lang="ko">' in scenario and '<meta charset="utf-8">' in scenario,
      'installer_page_complete':'91c93e6fed0f86e4fe07fe2ee45df96c1ce08ff4c2ee67a610d3189daf9349a4' in installer and 'found no threats' in installer and installer.count("class='pass'>PASS")>=14,
      'installer_reports_exact':reports_exact,
      'no_temp_files':not any(p.name.startswith('.cgko_') or p.suffix.lower()=='.tmp' for p in pkg.rglob('*') if p.is_file()),
      'installed_false':summary.get('installed_to_game') is False and summary.get('live_original_unchanged') is True,
    }
    result={'status':'PASS' if all(checks.values()) else 'FAIL','package':str(pkg),'package_file_count':len(actual)+1,'manifest_entries':len(expected),'checks':checks,'manifest_sha256':h(pkg/'package_sha256_manifest.json')}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())