# 크리미널 걸즈 인바이트 온리 PC(스팀)판 한국어 패치 작업물

비공개 보관용 저장소. 패치 코드·도구·번역 텍스트만 담는다.

원본 게임 파일, 추출한 원문 데이터, 그림·음성·영상, 실행 파일과 빌드 결과는 넣지 않았다.
패치를 다시 만들려면 원본 게임이 따로 필요하다.

## 폴더 구성

| 폴더 | 내용 |
|---|---|
| `pc-steam/` | Codex 쪽 한국어 패치 — 번역(`translation/`), 데이터 변환(`adapter/`), 도구(`tools/`), 설치기(`installer/`), 배포본 스크립트(`release/korean_patch_jp_voicefix_20260901/`), 검증 보고서(`release/reports/`), 문서(`docs/`) |
| `pc-cheats-mods/` | Claude 쪽 설정 화면 치트·모드 DLL 소스(`src/*.c`), 도구(`tools/*.py`), 시험판 설치 스크립트, 작업 기록(`진행.md`) |
| `assets-ko/` | 한국어 그림 패치 데이터(`patch-data_jp/` — `.imy` 41개, `.ptm` 5개)와 PNG 미리보기 |

## 추가·변경 사항

원판 스팀판(Criminal Girls Invite Only, `steam_criminal.exe`) 대비 이 패치가 바꾸는 것을 정리했다. 근거는 괄호 안에 적었고, 기록만으로 확정할 수 없는 것은 「(추정)」으로 표시했다.

### 대상 판본

- 스팀판 일본어 데이터 `data/data_jp.dat`(1,931,410,944 B)와 `steam_criminal.exe`(1,929,728 B)가 배포본 manifest의 기준 해시와 정확히 일치할 때만 설치된다 (`release/korean_patch_jp_voicefix_20260901/README_KO.txt`, `PatchCommon.ps1`).
- 패치 후 `data_jp.dat`은 1,933,754,880 B, exe는 2,518,528 B가 되고, exe에는 `.koinput`·`.kostate` 섹션이 추가된다 (같은 배포본 manifest).
- 한국어는 **일본어 슬롯을 덮어쓴다**. `data/data_en.dat`은 건드리지 않는다. 게임 설정에서 **Japanese text**를 골라야 한국어가 나오고, Tomoe 같은 영어 이름이 보이면 영어 슬롯이 선택된 상태다 (`README_KO.txt`, `completion_audit_v9.json`의 `translation_contract`).

### 번역 범위

- 일본어 원문 기준 전체 한국어화: 시나리오(BSCR) 48,296곳, 시나리오 외 텍스트 2,709행, exe 문자열 63개, UI 그림 36종(압축 항목 72개), 완성형 한글 2,350자 폰트 (`release/reports/completion_audit_v9.json`의 `coverage`).
- 시나리오는 Antigravity 번역을 바탕으로 Codex 내부 모델이 품질 수정을 했다 (`release/scenario_antigravity_codex_qualityfix_20260830/`, `README_KO.txt`).
- 2026-09-01 전투 보이스 수정판에서 추가로 고친 것 (`README_KO.txt`, `docs/TOMOE_VOICE_POLICY_20260901.md`):
  - 토모에의 간사이 사투리를 부드러운 경상권 사투리로 복원하고, `センセ`는 「쌤」으로 옮겼다. 적용 범위는 전투 보이스 56행, 필드 30행, 오더 진행 10행, 벌주기 23행이다.
  - 란·키사라기·앨리스·사코·유코·신의 전투 말투와 오역 7건을 교정했다.
  - 시나리오 외 고유 119행을 고쳤고, 실제 표시 위치로는 655곳이다.
  - 이름표 「토모에」와 「하루카와 토모에」의 런타임 인코딩을 검증했다.
- 메인 타이틀 메뉴(NEW GAME 등)는 2026-08-16 기록 기준으로 한국어 표시에 한 번도 성공하지 못했다. 그 뒤 배포본에서 해결됐는지는 기록에서 확인하지 못했다 (`docs/HANDOFF_CLAUDE_MAIN_MENU_FAILURE.md`) (추정: 영문 그대로).

### 편의 기능

- **한국어 이름 입력**: 두벌식 한글 조합, 영문·숫자 입력, 최대 6글자 (`completion_audit_v9.json`의 `runtime.name_input`).
- **설정 화면 「치트」·「모드」 줄** (Claude 쪽 시험판, `pc-cheats-mods/`): 음량 설정 아래에 두 줄을 추가했고 마우스로도 조작된다 (`src/options.c`, `진행.md`).
  - 치트 8종: 무적, MP 소모 없음, 경험치 배율, 돈 배율(1~20배), 인카운터 끔, 이동 속도(1.5·2·3배), 전투 속도(2·3·4배), CG·회상 전부 개방 (`src/pc_strings.c`, `src/options.c`).
  - 실측으로 확인된 것은 무적, 경험치·돈 배율, MP 소모 없음이다. 이동 속도, 인카운터 끔, CG 개방은 아직 실측하지 않았다 (`진행.md`).
  - 모드 3종: 전투 음성 말풍선, 주제가 가사 자막, 검열 해제 모드. 검열 해제 모드는 `data\kor_decensor.dat`가 있을 때만 보인다 (`src/pc_strings.c`, `src/options.c`의 `items()`).
- **전투 음성 말풍선**: 전투 보이스 1,219개 키(134묶음)를 반투명 검정 상자 안에 흰 굵은 글씨로 띄운다 (`src/subs.c`, `src/pc_subs_table.c`, `진행.md`).
- **비타 세이브 가져오기**: 비타판 세이브를 PC판 형식으로 바꾼다 (`tools/vita_saves_to_pc.py`).
- **검열 해제 모드**: 비타용 「CGIO - Mod + Decensor」 그림 37장을 PC 팔레트(R/B 교환)로 옮긴 덮어쓰기 데이터다. 게임을 다시 켜야 적용된다 (`tools/make_pc_decensor.py`, `src/decensor.c`, `tools/gen_pc_strings.py`).
- 설정은 세이브 폴더의 `kor_options.bin`에 저장되고, 동작 기록은 `kor_hook.log`에 남는다 (`진행.md`).

### 단축키·조작

- 이름 입력 화면에서 쓰는 키 (`completion_audit_v9.json`의 `help_legend`):
  - **F1**: 한/영 전환
  - **Backspace**: 삭제
  - **마우스 클릭**: 일본어 입력
  - **Enter**: 완료
- 치트·모드 줄은 게임 커서와 마우스로 조작한다. 별도 단축키는 소스에서 찾지 못했다 (`src/options.c`).

### 화면·그래픽 개선

- 한국어 UI 그림은 원본의 위치·크기·색·정렬을 유지하도록 다시 그렸다 (`assets-ko/patch-data_jp/`, `adapter/build_encoded_ui.py`, `HANDOFF_CLAUDE_MAIN_MENU_FAILURE.md`의 시각 요구사항).
- 런타임 한글 폰트 아틀라스를 만들어 넣었다 (`adapter/build_korean_font.py`, `adapter/build_runtime_font_atlas.py`).
- 말풍선 글자의 세로 가운데 정렬을 바로잡았다 (`진행.md`).

### 버그 수정

- 배포본에서 고친 전투 말투·오역 7건과 시나리오 외 119행은 「번역 범위」에 적었다.
- 게임 자체 버그를 고쳤다는 기록은 찾지 못했다.

### 설치·제거 방식

- **한국어 패치** (`release/korean_patch_jp_voicefix_20260901/`, PowerShell) — 4단계로 나뉜다.
  1. `Verify-KoreanPatch.ps1`: 설치 전에 기준 해시를 검사한다.
  2. `Install-KoreanPatch.ps1 -GameRoot … -BackupRoot …`: 설치한다. 백업 폴더는 게임 폴더와 패키지 폴더 밖이어야 한다.
  3. `Recover-KoreanPatch.ps1`: 중단된 설치를 복구한다.
  4. `Restore-KoreanPatch.ps1`: 원본으로 되돌린다.
  - 어느 단계든 실행 전에 `steam_criminal.exe`를 종료해야 한다.
  - 네 스크립트와 공통 모듈 `PatchCommon.ps1`이 모두 이 폴더에 있다. 실제 패치 데이터는 저장소에 없으므로 배포 ZIP이 따로 필요하다 (추정).
- **치트·모드 시험판** (`pc-cheats-mods/PC 시험판 설치 (설정 치트·모드).ps1`) — 게임 파일을 바꾸지 않는다.
  - 게임 폴더에 대리 `xinput1_3.dll`을 두는 방식이다. 이 DLL은 원래 함수(서수 2~8)를 그대로 넘기고, 실행 중에 메모리를 패치한다.
  - 패치하기 전에 ASLR 기준 주소를 보정하고 원래 바이트가 맞는지 확인한다 (`src/hook.c`, `src/stubs.S`, `진행.md`).
  - 제거는 DLL을 지우면 된다 (추정).

### 판별 변경 기록

| 날짜 | 내용 | 근거 |
|---|---|---|
| 2026-08-13 | 설치기 v2 소스 | `installer/` (source_v2_20260813) |
| 2026-08-16 | 메인 메뉴 한국어화 실패 분석 인계 | `docs/HANDOFF_CLAUDE_MAIN_MENU_FAILURE.md` |
| 2026-08-30 | 시나리오 품질 수정판 | `release/scenario_antigravity_codex_qualityfix_20260830/` |
| 2026-09-01 | 전투 보이스 수정판(최신 배포본), 완료 감사 v9 | `release/korean_patch_jp_voicefix_20260901/`, `reports/completion_audit_v9.json` |
| 2026-11-22~23 | 치트·모드 DLL, 말풍선, 비타 세이브, 검열 해제 모드 (DLL 20261123f) | `pc-cheats-mods/진행.md` |
| 2026-11-25 | 저장소 정리 | 455e44b, 642f9a4, cbb17a8 |

### 알려진 문제

- 전투 속도 ×3에서 전투가 시작될 때 검은 띠와 UI 조각이 잠깐 깜빡인다 (`진행.md`).
- 속도 치트가 판별에 쓰는 비트 22 때문에 일부 스토리 장면이 전투로 취급될 수 있다 (`진행.md`).
- 치트·모드 줄이 영어 도트 글꼴 그림과 나란히 있어 어색해 보인다 (`진행.md`).
- 외부 「CGIO Mod Loader」는 exe 체크섬을 검사하므로, 한국어판 exe에서는 패치를 거부할 수 있다 (`진행.md`, 설치하지 않음).
- 남은 작업 (`진행.md`):
  - 주제가 가사 자막
  - 비타판의 09-01 이후 수정(v21 616행, v22 그림 72장)을 PC로 옮기기
  - 검열 해제 그림 내용은 사용자가 직접 확인해야 한다
- 메인 타이틀 메뉴는 영문으로 남아 있을 수 있다 (추정, 위 「번역 범위」 참고).
