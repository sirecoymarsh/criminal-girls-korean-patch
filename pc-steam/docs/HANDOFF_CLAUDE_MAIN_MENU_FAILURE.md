# Claude 핸드오프 — 메인 메뉴 한국어화 실패 분석

작성일: 2026-08-16 (KST)  
대상 게임: **Criminal Girls Invite Only (Windows/Steam 계열 빌드)**  
프로젝트 루트: `P:\AI\Codex\projects\criminal-girls-invite-only-ko`  
원본 설치 입력: `F:\DOWN\Criminal.Girls.Invite.Only\Criminal.Girls.Invite.Only\Criminal Girls Invite Only`

## 1. 요청 목표

메인 타이틀 메뉴의 영문 표기를 한국어로 바꾼다.

| 원문 | 목표 번역 |
|---|---|
| NEW GAME | 새 게임 |
| LOAD GAME | 불러오기 |
| CONTINUE | 이어하기 |
| OPTION / OPTIONS | 설정 |
| EXIT GAME | 게임 종료 |
| ART GALLERY | 일러스트 갤러리 |
| SCENE GALLERY | 장면 갤러리 |
| ??? | 그대로 유지 |
| PRESS ANY BUTTON | 아무 버튼이나 누르세요 |

시각 요구사항은 원본의 위치·크기·색상·정렬·장식·선택 상태를 유지하고, 원문 흔적이나 검은 덮개 없이 자연스럽게 만드는 것이다.

## 1.1 사용자 정정 — 성공 사례는 0회

이 항목은 다른 모든 기술 설명보다 우선한다.

- **한국어 메인 메뉴가 실제 게임 화면에 표시된 적은 단 한 번도 없다.**
- `새 게임`, `불러오기`, `이어하기`, `설정`, `게임 종료` 중 어느 하나도 런타임 메뉴에 부분적으로라도 나타난 적이 없다.
- 성공에 가까운 빌드나 부분 성공 빌드도 없었다.
- 관찰된 결과는 세 종류뿐이었다.
  1. 원래 대문자 영문 메뉴가 그대로 표시됨
  2. 타이틀 메뉴 그림이 검게 사라짐
  3. 영문 메뉴는 남고 금색 선택 프레임만 깨짐
- 아래의 “원본 재압축 성공”은 **압축된 원본 영문 데이터를 다시 넣었을 때 영문 메뉴가 유지됐다는 저수준 코덱 시험**일 뿐이다. 메뉴 한국어화 성공이나 부분 성공으로 해석하면 안 된다.
- 정적 PNG에서 한국어가 보였다는 사실도 게임 내 출력 증거가 아니다.
## 2. 현재 상태와 안전 기준

- **메인 메뉴 한국어화는 아직 완료되지 않았다.** 현재 실행 메뉴는 영문이다.
- 실패한 FAD 시험 변경은 모두 자동 복원했다.
- 현재 P 런타임 아카이브의 복원 확인 SHA-256:
  - `P:\AI\Codex\projects\criminal-girls-invite-only-ko\workspace\runtime_latest\data\data_jp.dat`
  - `31DB8E54CB1E8F333FBFCBC9C39866F9B4D277CD0A216BB67D2A7E6249BC0F95`
- 위 해시는 순정 게임 해시가 아니라, 이미 정상 동작하는 한글 폰트·이름 입력기 등이 포함된 **이 프로젝트의 메인 메뉴 작업 전 기준본**이다.
- `data_jp.dat`와 `data_en.dat`는 같은 물리 파일을 가리키는 하드링크다. 한쪽을 직접 수정하면 다른 쪽도 동시에 바뀐다.
- F 드라이브 원본은 수정하지 않았다.
- 현재 `steam_criminal.exe` 시험 프로세스는 실행 중이지 않다.
- 기존 한글 대사 출력과 이름 입력 시스템은 동작하므로 메인 메뉴 작업 때문에 실행 파일·폰트·입력기 패치를 되돌리거나 교체하면 안 된다.
- 사용자가 시험 실행 중 전체화면·잘못된 영문판·반복 실행을 여러 번 겪었다. 이후 작업은 먼저 정적으로 증명하고, 실제 실행은 **창모드 최신 P 빌드로 한 번에 모아서** 검증해야 한다.

## 3. 결론부터: 왜 실패했는가

### 확정된 직접 원인

**실제 화면에 보이는 메뉴 글자의 소비자와 수정한 래스터 아틀라스의 소비자를 동일하다고 잘못 판단했다.**

수정한 FAD stream 26에는 `New Game`, `Load Game`, `Continue` 같은 혼합 대소문자 영문 래스터와 금색 선택 프레임이 같이 보인다. 그러나 실제 PC 런타임 메뉴는 `NEW GAME`, `LOAD GAME`, `CONTINUE`처럼 전부 대문자로 표시된다.

결정적인 분할 시험에서 stream 26의 앞쪽 네 문구라고 추정한 영역을 바꿨을 때도 한국어 문구는 단 하나도 출력되지 않았고:

1. 한국어는 나타나지 않았다.
2. 기존 대문자 영문 메뉴는 그대로 남았다.
3. 대신 `NEW GAME` 주변의 금색 선택 프레임 일부가 깨졌다.

즉, stream 26의 눈에 보이는 혼합 대소문자 표기는 실제 PC 메뉴 글자와 동일한 표시면이 아니며, 우리가 글자 영역이라 가정한 좌표는 런타임에서는 선택 프레임 또는 다른 장식에 소비되고 있었다. **텍스처를 찾은 것과 실제 UI 소비자/UV 소유권을 찾은 것을 혼동한 것이 핵심 실패다.**

### 아직 미확정인 부분

실제 대문자 메뉴 글자가 다음 중 어디서 오는지는 아직 확정하지 못했다.

- FAD 내부의 다른 텍스처/밉/레이어
- `TITL_TXT` 애니메이션 정의가 참조하는 별도 글자 레이어
- 게임 공용 폰트로 런타임 렌더링되는 문자열
- 별도 스크립트/로컬라이즈 테이블/실행 파일 상수

따라서 다음 담당자는 곧바로 새 한국어 그림을 그리지 말고 **실제 대문자 `NEW GAME` 픽셀 또는 문자열이 어디에서 만들어지는지 먼저 증명**해야 한다.

## 4. 실패 경과

### 4.1 바깥쪽 `title.0001.imy` 수정 — 런타임 미사용

처음에는 메인 아카이브의 외부 `title.0001.imy`를 PC 타이틀 메뉴로 판단해 한국어 래스터를 만들었다. 컨테이너 왕복과 정적 이미지 자체는 정상이고 원문 제거/배치도 가능했지만, 게임은 계속 영문 메뉴를 표시했다.

후속 `fread` IAT 추적으로 타이틀 진입 시 실제 읽기 흐름을 확인했다.

- 읽힘: `title.tpk`, `anm0000.fad`, 타이틀 음악
- 직접 읽기 증거 없음: 외부 `title.0000/0001/0006/...` IMY 묶음

따라서 외부 `title.0001.imy`는 현재 PC 메뉴의 실효 표시면이 아니다. `title.tpk` 안의 `title.asbin`이 `TITLE.0001.imy` 문자열을 가진다는 사실만으로 런타임 소비를 증명할 수 없었다.

### 4.2 실제 읽히는 `anm0000.fad` 발견

메인 아카이브에서 다음 항목이 실제 읽혔다.

- 아카이브 엔트리: `anm0000.fad`
- 엔트리 index: `281`
- 크기: `133,978,376` bytes
- 메인 아카이브 내 offset: `1,614,939,648`
- 추출본: `C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\anm0000.fad`

FAD에는 `YKCMP_V1` 스트림 117개가 있다. 스캔 보고서:

`C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\anm0000_fad_scan.json`

### 4.3 FAD stream 26을 메뉴 아틀라스로 오인

stream 26 정보:

- FAD 상대 헤더 offset: `29,638,224` (`0x01C43E50`)
- 메인 아카이브 내 헤더 절대 offset: `1,644,577,872`
- 압축 payload 절대 offset: `1,644,577,892`
- 압축 크기 필드: `156,668` (`0x263FC`)
- 20바이트 `YKCMP_V1` 헤더를 제외한 실제 payload 용량: `156,648`
- 비압축 크기: `4,194,304` = 1024×1024×4 BGRA 계열
- 원본 메타데이터 10개 `u32`:
  - `[0x26430, 0, 0x263fc, 0x400000, 0x04000400, 0x01200000, 0, 2, 0x00c0fe3c, 0x77360976]`
- stream 직후에 `TITL_TXT` 정의가 이어진다.

디코딩한 검정 배경 미리보기:

`C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\all_4mb_streams\stream_026.jpg`

이 이미지에는 혼합 대소문자 메뉴 문구와 금색 프레임이 함께 있어서 실제 메뉴 텍스처처럼 보였다. 이 시각적 유사성 때문에 소비자/UV 검증 없이 패치를 진행한 것이 잘못이었다.

### 4.4 YKCMP 압축 및 삽입 시험

구현 파일:

- `C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\fad_ykcmp_tool.py`
- `C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\build_fad_title_korean.py`
- `C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\probe_fad_title_korean.py`

확인된 사실:

- 원본 4 MiB raw를 자체 압축기로 재압축한 payload는 `152,296` bytes였다.
- 자체 디코더로 압축→해제 byte identity PASS.
- 스위즐 해제→재스위즐도 원본 raw와 byte identity PASS.
- **재압축한 원본 raw를 같은 위치에 넣었을 때 실제 게임 메뉴가 정상 출력됐다.**
- 정상 캡처:
  - `C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\fad_title_ko\runtime_probe_original_recompressed.png`

따라서 **원본 영문 raw를 그대로 보존하는 경우에 한해서** YKCMP 코덱과 in-place 교체 경로가 영문 화면을 다시 표시할 수 있다는 것만 확인됐다. 한국어 메뉴 출력은 0회이며, 이 시험을 메뉴 한국어화의 부분 성공으로 분류하면 안 된다.

### 4.5 첫 삽입 코드의 20바이트 경계 실수

초기 probe는 `156,668`을 payload 길이로 잘못 취급해 헤더 다음부터 156,668바이트를 쓰면서 원래 payload 경계 뒤 20바이트까지 임시로 덮었다. 또한 내부 압축 크기 필드를 새 payload 길이에 맞춰 줄였다. 이 시험은 검은 화면을 만들었다.

이후 다음과 같이 수정했다.

- `156,668`은 20바이트 YKCMP 헤더를 포함한 span으로 취급
- payload 용량은 `156,648`
- FAD 리소스 테이블과 헤더의 원래 크기 필드를 유지
- 새 payload 뒤는 원래 payload span 안에서만 0으로 패딩
- probe 종료 시 원본 bytes 복원 후 전체 아카이브 SHA-256 확인

경계 실수는 자동 복원됐고 현재 런타임에 잔존하지 않는다.

### 4.6 전체 한국어 후보 — 검은 타이틀 화면

한국어 후보:

- 아틀라스: `...\title_ui_review\fad_title_ko\atlas_ko_q8.png`
- 검정 배경 미리보기: `...\title_ui_review\fad_title_ko\atlas_ko_q8_black.jpg`
- YKCMP payload: `...\title_ui_review\fad_title_ko\stream26_ko_q8.payload`
- payload 크기: `151,474` bytes

정적 아틀라스는 한국어가 정상으로 보이고 허용 영역 밖 변경 0으로 만들었지만, 실제 런타임에서는 로고 뒤 타이틀 화면이 검게 남았다.

캡처 묶음:

`C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\runtime_title_capture\ko_probe_35_65_contact.jpg`

이 현상만 보았을 때는 압축 문제처럼 보였으나, 재압축 원본 성공과 다음 분할 시험 때문에 최종적으로는 **수정 영역이 실제 표시면/장식 소유권과 맞지 않는 문제**가 더 근본적이라는 결론에 도달했다.

### 4.7 앞쪽 네 항목만 바꾼 분할 시험 — 결정적 증거

payload:

`C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\fad_title_ko\stream26_ko_first4.payload`

캡처:

`C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review\fad_title_ko\runtime_probe_first4.png`

실행 결과:

- 타이틀 배경과 영문 메뉴가 표시됨
- `NEW GAME`, `LOAD GAME`, `CONTINUE`, `OPTION`은 여전히 영문
- `NEW GAME` 선택 금색 프레임 일부가 깨짐
- 한국어는 표시되지 않음

이 결과로 stream 26의 미리보기상 글자 좌표와 실제 PC 런타임의 대문자 메뉴 글자 소비자가 일치하지 않는다는 점이 확정됐다.

## 5. 중요한 보조 발견

### 5.1 실제 런타임과 stream 26의 글꼴/대소문자가 다름

- stream 26 미리보기: `New Game`, `Load Game`, `Continue`, `Options`, `Exit Game`
- 실제 PC 런타임: `NEW GAME`, `LOAD GAME`, `CONTINUE`, `OPTION`, `EXIT GAME`

이 차이를 초기에 소비자 불일치 신호로 취급했어야 했다.

### 5.2 FAD 인접 스트림

- stream 27은 메뉴가 아니라 OP/레벨/대화 금지 등 다른 UI 아틀라스다.
  - `...\title_ui_review\all_4mb_streams\stream_027.jpg`
- stream 28은 512×64 숫자/기호 스트립이다.
  - 비교 디코드: `...\title_ui_review\stream28_variants.jpg`
- 1024×1024 스트림 비교표:
  - `...\title_ui_review\all_4mb_streams\contact_0.jpg`
  - `...\title_ui_review\all_4mb_streams\contact_1.jpg`

단, 117개 전체에는 1024×1024 이외의 512×512, 2048×2048, 1920×1088, 1536×1024 등 여러 텍스처가 있다. 1024×1024 후보만 본 것으로 실제 글자 소스를 배제해서는 안 된다.

### 5.3 아카이브 정적 문자열 검색

P 런타임 아카이브/실행 파일에서 ASCII 및 UTF-16 문자열을 직접 검색했다.

- `CONTINUE`, `OPTION`은 FAD 애니메이션 메타데이터/식별자 위치에서 발견됨
- 완전한 `NEW GAME`, `LOAD GAME`, `EXIT GAME`, `PRESS ANY BUTTON` 문자열은 원시 아카이브 검색에서 발견되지 않음
- 실행 파일에는 일반적인 `OPTION`/`Options`가 있으나 메인 메뉴 전용이라고 증명되지 않음

따라서 실제 메뉴가 단순 평문 문자열 테이블이라는 증거도 아직 없다. 글자가 래스터 조각/글리프 ID/압축된 스크립트에서 조합될 가능성이 있다.

### 5.4 런타임 메모리 영문 문자열 스캔은 완료되지 않음

메뉴가 표시되는 약 62초 시점에 `NEW GAME` 등을 ASCII/UTF-16/UTF-32로 스캔하려 했으나, 사용자가 중지를 요청하면서 프로세스가 먼저 종료되어 유효 결과가 없다. 이를 음성 증거로 사용하면 안 된다.

## 6. 다음 담당자에게 권장하는 해결 순서

### 1단계 — 변경 없이 실제 메뉴 소비자 증명

1. 현재 해시 `31DB...`를 확인한다.
2. 실제 런타임 실행 파일은 다음만 사용한다.
   - `P:\AI\Codex\projects\criminal-girls-invite-only-ko\workspace\runtime_latest\steam_criminal.exe`
   - 가능하면 `Launch-Korean-Windowed.lnk`
3. 사용자 승인 전에는 실행하지 말고 정적 분석부터 한다.
4. FAD의 `TITL_TXT` 블록을 구조적으로 파싱해 각 애니메이션 ID와 텍스처 index, UV 사각형, 상태 프레임의 연결을 만든다.
5. `NEW GAME` 실제 화면 픽셀과 후보 텍스처를 템플릿 매칭한다. 1024×1024 스트림만 보지 말고 메타데이터의 width/height를 이용해 117개 전체를 올바른 직사각 Morton/타일 스위즐로 디코딩한다.

### 2단계 — 가장 확실한 런타임 추적

정적 매칭으로 확정되지 않으면 다음 중 하나를 사용한다.

- YKCMP 해제 직후 4 MiB raw의 SHA-256과 원본 FAD stream index를 기록하는 좁은 후킹
- D3D9 `CreateTexture`/`LockRect`/업로드 직전의 원본 메모리 해시를 기록해 화면에 쓰인 텍스처와 FAD stream을 매핑
- 타이틀 메뉴가 표시된 단 한 시점에서 대문자 메뉴 픽셀의 텍스처 좌표를 잡고, 해당 GPU 업로드 원본만 역추적
- 동적 텍스트로 판명될 경우에만 텍스트 렌더러 호출 인자 또는 메뉴 문자열 공급 함수를 추적

목표는 “이 파일이 비슷해 보인다”가 아니라 다음을 증명하는 것이다.

> 특정 source entry/stream/UV 또는 문자열 UID의 한 글자만 시험 변경했을 때 실제 `NEW GAME`의 그 글자만 바뀌고, 금색 프레임과 다른 UI는 byte/pixel 불변이다.

이 단일 글자 증명이 없으면 한국어 전체 삽입을 진행하지 않는다.

### 3단계 — 실제 소스 유형에 맞춰 구현

#### 실제 글자가 동적 문자열이면

- 기존 한글 폰트/런타임 텍스트 코덱을 재사용한다.
- 표시 문자열만 stable UID 기준으로 바꾼다.
- 내부 식별자인 `CONTINUE`, `OPTION`, `TITL_TXT`를 번역하지 않는다.
- 원본 메뉴의 중심선, 크기, 색상, 선택 상태를 실제 캡처로 확인한다.

#### 실제 글자가 래스터면

- 정확한 소비자 UV와 상태별 레이어를 먼저 닫는다.
- 선택 프레임/금색 장식은 완전히 보존한다.
- 원문 글리프 얼굴, 외곽선, 그림자, 안티앨리어싱을 source-derived mask로만 제거한다.
- 검은 사각형이나 넓은 덮개를 쓰지 않는다.
- 원본 글자의 실제 footprint와 baseline에 한국어를 맞춘다.
- normal/selected/disabled/Press Any Button 상태를 모두 확인한다.

### 4단계 — 단 한 번의 통합 실행 QA

정적 검증이 끝난 후 사용자 승인을 받고 창모드 최신 P 빌드로 한 번만 실행한다.

필수 확인:

- 로고 이후 검은 화면 없음
- 새 게임/불러오기/이어하기/설정/게임 종료
- 저장 데이터 유무에 따른 활성/비활성 상태
- 일러스트 갤러리/장면 갤러리/???
- `아무 버튼이나 누르세요`
- 선택 프레임 이동 시 깨짐/잔상 없음
- 메뉴 선택 후 기존 한글 대사와 이름 입력기 회귀 없음

## 7. 수정 금지 및 주의사항

- F 드라이브 원본 수정 금지.
- P 런타임의 1.9 GB 아카이브를 무백업 상태로 직접 실험하지 말 것.
- `data_jp.dat`/`data_en.dat` 하드링크 관계를 잊지 말 것.
- 실패한 q8/first4 payload를 최종 빌드에 넣지 말 것.
- 진단 DLL/후킹 도구를 최종 게임 또는 배포본에 포함하지 말 것.
- 외부 `title.0001.imy`가 실제 메뉴라는 가정을 재사용하지 말 것.
- stream 26의 혼합 대소문자 글자가 실제 대문자 메뉴라고 가정하지 말 것.
- `TITL_TXT`, `CONTINUE`, `OPTION` 같은 내부 식별자를 표시 문자열이라고 단정하지 말 것.
- 시험 종료 후 반드시 전체 아카이브 해시가 `31DB...`로 복구됐는지 확인할 것.

## 8. 핵심 파일 목록

### P 프로젝트

- 런타임: `P:\AI\Codex\projects\criminal-girls-invite-only-ko\workspace\runtime_latest`
- 실행 파일: `P:\AI\Codex\projects\criminal-girls-invite-only-ko\workspace\runtime_latest\steam_criminal.exe`
- 메인 아카이브: `P:\AI\Codex\projects\criminal-girls-invite-only-ko\workspace\runtime_latest\data\data_jp.dat`
- 아카이브 파서: `P:\AI\Codex\projects\criminal-girls-invite-only-ko\adapter\archive_repack.py`
- 외부 IMY 원본 감사본: `P:\AI\Codex\projects\criminal-girls-invite-only-ko\extracted\ui_common_audit\imy\title.0001.imy`
- 외부 IMY 한국어 후보(실효 소비 미증명): `P:\AI\Codex\projects\criminal-girls-invite-only-ko\staging\ui_common_v2\outer\title.0001.imy`

### C 연구 작업공간

- 루트: `C:\Users\CadriacLord\Documents\Codex\2026-08-12\f-down-criminal-girls-invite-only\title_ui_review`
- FAD 추출본: `...\anm0000.fad`
- FAD 스캔: `...\anm0000_fad_scan.json`
- YKCMP 도구: `...\fad_ykcmp_tool.py`
- 한국어 후보 빌더: `...\build_fad_title_korean.py`
- 임시 probe: `...\probe_fad_title_korean.py`
- `fread` 추적 소스/바이너리: `...\fread_trace_hook.c`, `...\fread_trace_hook.dll`, `...\run_fread_trace32.exe`
- stream 26 미리보기: `...\all_4mb_streams\stream_026.jpg`
- 정상 재압축 원본 캡처: `...\fad_title_ko\runtime_probe_original_recompressed.png`
- 잘못된 first4 캡처: `...\fad_title_ko\runtime_probe_first4.png`
- 검은 화면 접촉표: `...\runtime_title_capture\ko_probe_35_65_contact.jpg`

## 9. Claude에게 전달할 작업 정의

**목표:** 실제 PC 런타임의 대문자 메인 메뉴 글자 소비자를 증명하고, 기존 한글 폰트/입력기 및 금색 프레임을 보존한 채 메뉴 표기만 한국어로 바꾼다.

**가장 먼저 할 일:** 이 문서와 위 파일을 읽고, 변경 없이 `TITL_TXT` 소비자 그래프 및 117개 FAD 텍스처의 실제 UV/stream 연결을 조사한다.

**완료 조건:**

1. 실제 `NEW GAME` 표시면의 source entry/stream/UV 또는 문자열 UID가 증거로 확정됨
2. 단일 글자 시험이 해당 메뉴 글자에만 영향을 줌
3. 한국어 전체 메뉴가 정상 표시됨
4. 금색 선택 프레임과 배경/로고가 원본과 동일함
5. 검은 화면, 깨짐, 원문 잔상, 글자 잘림 없음
6. 기존 한글 대사/이름 입력/창모드 실행 회귀 없음
7. 변경 전후 해시와 정확한 변경 범위, 복원 방법이 기록됨

---

요약하면, **게임 안에서 한국어 메뉴가 출력된 적은 0회다.** 확인된 것은 원본 영문 데이터의 재압축 왕복뿐이며 이는 현지화 성공이 아니다. 이번 시도는 비슷하게 생긴 아틀라스를 실제 UI 소비자로 오인해 영문 메뉴를 그대로 두거나 화면/프레임만 깨뜨렸다. 다음 작업은 기존 후보를 고치는 것이 아니라 실제 대문자 메뉴 글자의 생성 경로를 처음부터 증명하는 데서 시작해야 한다.

