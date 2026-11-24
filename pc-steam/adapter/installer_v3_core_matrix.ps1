[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][string]$BaselineFixture,
    [Parameter(Mandatory=$true)][string]$RunningGameRoot,
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$Report
)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Assert([bool]$Condition,[string]$Message){if(-not $Condition){throw $Message}}
function Invoke-Patch([string]$Pkg,[string]$Script,[string]$Game,[string]$Backup){
  $old=$ErrorActionPreference;$ErrorActionPreference='Continue'
  try{$o=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Pkg $Script) -GameRoot $Game -BackupRoot $Backup 2>&1;$c=$LASTEXITCODE}
  finally{$ErrorActionPreference=$old}
  [pscustomobject]@{Code=$c;Text=(($o|ForEach-Object{$_.ToString()})-join "`n")}
}
function Invoke-Verify([string]$Pkg,[string]$Game=''){
  $old=$ErrorActionPreference;$ErrorActionPreference='Continue'
  try{if($Game){$o=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Pkg 'Verify-KoreanPatch.ps1') -GameRoot $Game 2>&1}else{$o=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Pkg 'Verify-KoreanPatch.ps1') 2>&1};$c=$LASTEXITCODE}
  finally{$ErrorActionPreference=$old}
  [pscustomobject]@{Code=$c;Text=(($o|ForEach-Object{$_.ToString()})-join "`n")}
}
function WriteJson([string]$Path,$Value){$parent=Split-Path -Parent $Path;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent -Force|Out-Null};[IO.File]::WriteAllText($Path,(($Value|ConvertTo-Json -Depth 16)+"`n"),(New-Object Text.UTF8Encoding($false)))}
function Reset-Original([string]$Game,[string]$Baseline){Copy-Item -LiteralPath (Join-Path $Baseline 'data\data_jp.dat') -Destination (Join-Path $Game 'data\data_jp.dat') -Force;Copy-Item -LiteralPath (Join-Path $Baseline 'steam_criminal.exe') -Destination (Join-Path $Game 'steam_criminal.exe') -Force}
$pkg=[IO.Path]::GetFullPath($Package).TrimEnd('\');$base=[IO.Path]::GetFullPath($BaselineFixture).TrimEnd('\');$work=[IO.Path]::GetFullPath($Workspace).TrimEnd('\');$run=[IO.Path]::GetFullPath($RunningGameRoot).TrimEnd('\')
$project=Split-Path -Parent (Split-Path -Parent $pkg);$allowed=[IO.Path]::GetFullPath((Join-Path $project 'workspace')).TrimEnd('\')+'\installer_v3_core_'
Assert ($work.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)) "Unsafe workspace path: $work"
Assert (-not(Test-Path -LiteralPath $work)) "Refusing existing workspace: $work"
$manifest=Get-Content -LiteralPath (Join-Path $pkg 'manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
$targets=@{};foreach($t in @($manifest.game.targets)){$targets[[string]$t.id]=$t}
Assert ((Hash (Join-Path $base 'data\data_jp.dat')) -eq [string]$targets.data_jp.baseline_sha256) 'baseline data mismatch'
Assert ((Hash (Join-Path $base 'steam_criminal.exe')) -eq [string]$targets.executable.baseline_sha256) 'baseline exe mismatch'
New-Item -ItemType Directory -Path $work,(Join-Path $work 'game'),(Join-Path $work 'game\data')|Out-Null
$game=Join-Path $work 'game';New-Item -ItemType HardLink -Path (Join-Path $game 'data\data_jp.dat') -Target (Join-Path $base 'data\data_jp.dat')|Out-Null;New-Item -ItemType HardLink -Path (Join-Path $game 'steam_criminal.exe') -Target (Join-Path $base 'steam_criminal.exe')|Out-Null
$cases=New-Object Collections.Generic.List[object]
function AddCase([string]$Name,$Details){[void]$cases.Add([ordered]@{name=$Name;status='PASS';details=$Details})}
# Package-only integrity.
$v=Invoke-Verify $pkg;Assert($v.Code -eq 0 -and $v.Text -match '"status"\s*:\s*"PASS"') 'package verify failed';AddCase 'package_integrity' @{exit=$v.Code}
# Exact running target path must be blocked before any write. RunningGameRoot is the current v17 QA process.
$runningBefore=@{data=(Hash (Join-Path $run 'data\data_jp.dat'));exe=(Hash (Join-Path $run 'steam_criminal.exe'))};$guardBackup=Join-Path $work 'guard_backup';$g=Invoke-Patch $pkg 'Install-KoreanPatch.ps1' $run $guardBackup;$runningAfter=@{data=(Hash (Join-Path $run 'data\data_jp.dat'));exe=(Hash (Join-Path $run 'steam_criminal.exe'))};Assert($g.Code -ne 0 -and $g.Text -match 'target game process is running' -and $runningBefore.data -eq $runningAfter.data -and $runningBefore.exe -eq $runningAfter.exe -and -not(Test-Path -LiteralPath $guardBackup)) 'exact process guard failed';AddCase 'exact_process_guard' @{exit=$g.Code;unchanged=$true}
# Same process name at another path must not block full two-target transaction.
$backup=Join-Path $work 'backup';$i1=Invoke-Patch $pkg 'Install-KoreanPatch.ps1' $game $backup;Assert($i1.Code -eq 0) 'full install failed';Assert((Hash (Join-Path $game 'data\data_jp.dat')) -eq [string]$targets.data_jp.patched_sha256) 'installed data mismatch';Assert((Hash (Join-Path $game 'steam_criminal.exe')) -eq [string]$targets.executable.patched_sha256) 'installed exe mismatch';$vk=Invoke-Verify $pkg $game;Assert($vk.Code -eq 0 -and $vk.Text -match '"game_state"\s*:\s*"korean"') 'installed verify failed';$i2=Invoke-Patch $pkg 'Install-KoreanPatch.ps1' $game $backup;Assert($i2.Code -eq 0 -and $i2.Text -match 'already_installed') 'idempotent install failed';$r1=Invoke-Patch $pkg 'Restore-KoreanPatch.ps1' $game $backup;Assert($r1.Code -eq 0) 'full restore failed';$vo=Invoke-Verify $pkg $game;Assert($vo.Code -eq 0 -and $vo.Text -match '"game_state"\s*:\s*"original"') 'restored verify failed';$r2=Invoke-Patch $pkg 'Restore-KoreanPatch.ps1' $game $backup;Assert($r2.Code -eq 0 -and $r2.Text -match 'already_restored') 'idempotent restore failed';AddCase 'full_install_verify_restore_idempotence_different_path_process' @{install=$i1.Code;verify_korean=$vk.Code;install_again=$i2.Code;restore=$r1.Code;verify_original=$vo.Code;restore_again=$r2.Code}
# Mixed state rejection without write.
Copy-Item -LiteralPath (Join-Path $pkg 'payload\steam_criminal.exe') -Destination (Join-Path $game 'steam_criminal.exe') -Force;$mixBefore=@{data=(Hash (Join-Path $game 'data\data_jp.dat'));exe=(Hash (Join-Path $game 'steam_criminal.exe'))};$mv=Invoke-Verify $pkg $game;$mi=Invoke-Patch $pkg 'Install-KoreanPatch.ps1' $game (Join-Path $work 'mixed_backup');$mixAfter=@{data=(Hash (Join-Path $game 'data\data_jp.dat'));exe=(Hash (Join-Path $game 'steam_criminal.exe'))};Assert($mv.Code -ne 0 -and $mv.Text -match '"game_state"\s*:\s*"mixed"' -and $mi.Code -ne 0 -and $mi.Text -match 'Current state: mixed' -and $mixBefore.data -eq $mixAfter.data -and $mixBefore.exe -eq $mixAfter.exe) 'mixed rejection failed';AddCase 'mixed_state_rejected' @{verify_exit=$mv.Code;install_exit=$mi.Code;unchanged=$true};Reset-Original $game $base
# Unknown baseline rejection without data write or state creation.
$exePath=Join-Path $game 'steam_criminal.exe';$fs=[IO.File]::Open($exePath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);try{$b=$fs.ReadByte();$fs.Position=0;$fs.WriteByte($b -bxor 255);$fs.Flush($true)}finally{$fs.Dispose()};$unknownHash=Hash $exePath;$dataBefore=Hash (Join-Path $game 'data\data_jp.dat');$ub=Join-Path $work 'unknown_backup';$u=Invoke-Patch $pkg 'Install-KoreanPatch.ps1' $game $ub;Assert($u.Code -ne 0 -and $u.Text -match 'Current state: unsupported' -and (Hash $exePath) -eq $unknownHash -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $dataBefore -and -not(Test-Path -LiteralPath $ub)) 'unknown rejection failed';AddCase 'unknown_baseline_rejected' @{exit=$u.Code;unchanged=$true};Reset-Original $game $base
# Tampered package rejected before target/backup write. Payloads are hardlinks; only copied README is changed.
$bad=Join-Path $work 'tampered_package';New-Item -ItemType Directory -Path $bad,(Join-Path $bad 'payload')|Out-Null;foreach($n in @('PatchCommon.ps1','Install-KoreanPatch.ps1','Recover-KoreanPatch.ps1','Restore-KoreanPatch.ps1','Verify-KoreanPatch.ps1','README_KO.txt','manifest.json')){Copy-Item -LiteralPath (Join-Path $pkg $n) -Destination (Join-Path $bad $n)};New-Item -ItemType HardLink -Path (Join-Path $bad 'payload\data_jp.dat') -Target (Join-Path $pkg 'payload\data_jp.dat')|Out-Null;New-Item -ItemType HardLink -Path (Join-Path $bad 'payload\steam_criminal.exe') -Target (Join-Path $pkg 'payload\steam_criminal.exe')|Out-Null;[IO.File]::AppendAllText((Join-Path $bad 'README_KO.txt'),'tamper',(New-Object Text.UTF8Encoding($false)));$badBefore=@{data=(Hash (Join-Path $game 'data\data_jp.dat'));exe=(Hash $exePath)};$bv=Invoke-Verify $bad;$bi=Invoke-Patch $bad 'Install-KoreanPatch.ps1' $game (Join-Path $work 'tamper_backup');$badAfter=@{data=(Hash (Join-Path $game 'data\data_jp.dat'));exe=(Hash $exePath)};Assert($bv.Code -ne 0 -and $bi.Code -ne 0 -and $badBefore.data -eq $badAfter.data -and $badBefore.exe -eq $badAfter.exe) 'tampered package rejection failed';AddCase 'tampered_package_rejected' @{verify_exit=$bv.Code;install_exit=$bi.Code;unchanged=$true}
# Exact script-byte bridge to the prior full negative/recovery matrix.
$prior=Join-Path $project 'release\korean_patch_jp_final_v2\manifest.json';$priorDoc=Get-Content -LiteralPath $prior -Raw -Encoding UTF8|ConvertFrom-Json;$priorScripts=@{};foreach($f in @($priorDoc.files)){if(([string]$f.path).EndsWith('.ps1')){$priorScripts[[string]$f.path]=[string]$f.sha256}};$newScripts=@{};foreach($f in @($manifest.files)){if(([string]$f.path).EndsWith('.ps1')){$newScripts[[string]$f.path]=[string]$f.sha256}};Assert($priorScripts.Count -eq 5 -and $newScripts.Count -eq 5) 'script bridge count mismatch';foreach($k in $newScripts.Keys){Assert($priorScripts[$k] -eq $newScripts[$k]) "script bridge mismatch: $k"};AddCase 'exact_script_regression_bridge' @{script_count=5;prior_full_matrix='release/reports/installer_release_verification_v2.json';byte_identical=$true}
$temps=@(Get-ChildItem -LiteralPath $game -Recurse -Force -File|Where-Object{$_.Name -like '.cgko_*'});Assert($temps.Count -eq 0) 'leftover transaction temp files'
$result=[ordered]@{schema='criminal-girls.installer-core-matrix.v3';status='PASS';package=$pkg;manifest_sha256=(Hash (Join-Path $pkg 'manifest.json'));data_payload_sha256=[string]$targets.data_jp.patched_sha256;exe_payload_sha256=[string]$targets.executable.patched_sha256;case_count=$cases.Count;cases=$cases;leftover_transaction_files=@($temps|ForEach-Object{$_.FullName});baseline_fixture_unchanged=((Hash (Join-Path $base 'data\data_jp.dat')) -eq [string]$targets.data_jp.baseline_sha256 -and (Hash (Join-Path $base 'steam_criminal.exe')) -eq [string]$targets.executable.baseline_sha256)}
WriteJson $Report $result;$result|ConvertTo-Json -Depth 16
