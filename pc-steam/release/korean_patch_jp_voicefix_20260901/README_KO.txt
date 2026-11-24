Criminal Girls Invite Only 한국어 패치 - 전투 보이스 수정판 (2026-09-01)

지원 기준
- 일본어판 원본 data/data_jp.dat와 steam_criminal.exe가 manifest.json의 기준 해시와 정확히 일치하는 설치본
- 일본어 슬롯(data/data_jp.dat)을 한국어로 교체하며 data/data_en.dat는 수정하지 않습니다.

포함 내용
- 누적 한국어 패치의 시나리오, 시나리오 외 텍스트, UI, 폰트와 한국어 이름 입력
- Antigravity 시나리오 번역에 대한 Codex 내부 모델 품질 수정
- 전투·필드·오더 진행·벌주기에서 토모에의 부드러운 경상권 사투리 복원
- 란·키사라기·앨리스·사코·유코·신의 전투 말투/오역 7건 교정
- 비시나리오 고유 119행, 실제 표시 위치 655곳 수정
- 이름표 `토모에`, `하루카와 토모에` 런타임 인코딩 검증

언어 선택
- 한국어는 일본어 슬롯입니다. 게임 설정에서 Japanese text를 선택해야 합니다.
- 영어 이름(Tomoe 등)이 보이면 영어 슬롯이 선택된 상태입니다.

설치 전 검사
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-KoreanPatch.ps1 -GameRoot "게임 폴더"

설치
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "게임·패키지 외부 백업 폴더"

중단 복구
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Recover-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "설치 때 사용한 백업 폴더"

원본 복원
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Restore-KoreanPatch.ps1 -GameRoot "게임 폴더" -BackupRoot "설치 때 사용한 백업 폴더"

설치·복원·복구 전에 대상 경로의 steam_criminal.exe를 종료해야 합니다.
