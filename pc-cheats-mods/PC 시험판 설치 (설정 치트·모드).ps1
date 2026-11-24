# 크리미널 걸즈 PC(Steam) 게임 폴더에 대리 xinput1_3.dll(설정 「치트」「모드」 줄 + 치트 갈고리 + 전투 음성 말풍선
# + 검열 해제 모드)과 data\kor_decensor.dat(비타 「CGIO - Mod + Decensor」를 PC 꼴로 옮긴 덮어쓰기 파일)을 넣는다.
# 게임 exe·자료 파일(data_jp.dat·data_en.dat)은 건드리지 않는다.
# 빼려면 게임 폴더의 xinput1_3.dll 과 data\kor_decensor.dat 를 지우면 원래대로.
param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
$game = 'F:\DOWN\Criminal.Girls.Invite.Only\Criminal.Girls.Invite.Only\Criminal Girls Invite Only'
$dll  = 'P:\AI\cg-battle-subs\pc\build\xinput1_3_20261123f.dll'
$ovl  = 'Y:\AI\claude-work\cg-pc\kor_decensor.dat'
function Wait-Close { if (-not $NoPause) { Read-Host '엔터로 닫기' | Out-Null } }

$running = Get-Process steam_criminal -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$game\*" }
if ($running) { Write-Host '게임이 켜져 있습니다. 끈 뒤 다시 실행하세요.' -ForegroundColor Yellow; Wait-Close; exit 1 }

$dst = Join-Path $game 'xinput1_3.dll'
if (Test-Path $dst) {
    $old = (Get-FileHash $dst).Hash.Substring(0,8)
    Copy-Item $dst (Join-Path $game "xinput1_3.dll.bak_$old") -Force
    Write-Host "이전 xinput1_3.dll 을 xinput1_3.dll.bak_$old 로 백업했습니다."
}
Copy-Item $dll $dst -Force
Write-Host ('완료: xinput1_3.dll ' + (Get-FileHash $dst).Hash.Substring(0,8)) -ForegroundColor Green
if (Test-Path $ovl) {
    $odst = Join-Path $game 'data\kor_decensor.dat'
    Copy-Item $ovl $odst -Force
    Write-Host ('완료: data\kor_decensor.dat ' + (Get-FileHash $odst).Hash.Substring(0,8)) -ForegroundColor Green
} else {
    Write-Host "덮어쓰기 파일이 없어 검열 해제는 넣지 않았습니다: $ovl" -ForegroundColor Yellow
}
Write-Host '타이틀 > OPTION 첫 쪽 맨 아래에 「치트」「모드」 줄이 생깁니다. 값은 SaveDataFolder\kor_options.bin 에 저장됩니다.'
Write-Host '전투 중 캐릭터 음성에 한국어 말풍선이 뜹니다(모드 > 전투 음성 말풍선 으로 켜고 끔).'
Write-Host '모드 > 검열 해제 모드: 켜져 있으면 벌주기 장면이 비타 Mod + Decensor 와 같게 나옵니다(바꾼 뒤 게임을 다시 켜야 적용).'
Wait-Close
