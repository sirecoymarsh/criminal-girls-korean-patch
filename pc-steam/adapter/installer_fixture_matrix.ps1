[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ReleasePackage,
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$Report
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Write-Utf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}
function Invoke-Patch([string]$Package, [string]$Script, [string]$Game, [string]$Backup) {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Package $Script) -GameRoot $Game -BackupRoot $Backup 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    [pscustomobject]@{Code=$code; Text=(($output | ForEach-Object { $_.ToString() }) -join "`n")}
}
function New-Game([string]$Name, [byte[]]$Data) {
    $game = Join-Path $Workspace $Name
    New-Item -ItemType Directory -Path (Join-Path $game 'data') -Force | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $game 'data\data_jp.dat'), $Data)
    Copy-Item -LiteralPath 'C:\Windows\System32\PING.EXE' -Destination (Join-Path $game 'steam_criminal.exe') -Force
    return $game
}
function No-Temps([string]$Game) {
    return @(Get-ChildItem -LiteralPath (Join-Path $Game 'data') -Force -File | Where-Object {$_.Name -like '.cgko_*'}).Count -eq 0
}
function Flip-FirstByte([string]$Path) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { $value = $stream.ReadByte(); $stream.Position = 0; $stream.WriteByte(($value -bxor 0xFF)); $stream.Flush($true) } finally { $stream.Dispose() }
}

$release = [IO.Path]::GetFullPath($ReleasePackage)
$workspaceFull = [IO.Path]::GetFullPath($Workspace)
if (Test-Path -LiteralPath $workspaceFull) { Remove-Item -LiteralPath $workspaceFull -Recurse -Force }
New-Item -ItemType Directory -Path $workspaceFull -Force | Out-Null

$baseline = New-Object byte[] (1024 * 1024)
$patched = New-Object byte[] (1024 * 1024)
for ($i=0; $i -lt $patched.Length; $i++) { $patched[$i] = 0x5A }
$baselineFile = Join-Path $workspaceFull 'baseline.dat'
$patchedFile = Join-Path $workspaceFull 'patched.dat'
[IO.File]::WriteAllBytes($baselineFile, $baseline)
[IO.File]::WriteAllBytes($patchedFile, $patched)
$baselineHash = Hash $baselineFile
$patchedHash = Hash $patchedFile

$package = Join-Path $workspaceFull 'mini_package'
$payloadDir = Join-Path $package 'payload'
New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
$scriptNames = @('PatchCommon.ps1','Install-KoreanPatch.ps1','Recover-KoreanPatch.ps1','Restore-KoreanPatch.ps1','Verify-KoreanPatch.ps1','README_KO.txt')
foreach ($name in $scriptNames) { Copy-Item -LiteralPath (Join-Path $release $name) -Destination (Join-Path $package $name) -Force }
Copy-Item -LiteralPath $patchedFile -Destination (Join-Path $payloadDir 'data_jp.dat') -Force
$roles = [ordered]@{
    'PatchCommon.ps1'='common'; 'Install-KoreanPatch.ps1'='install'; 'Recover-KoreanPatch.ps1'='recover'
    'Restore-KoreanPatch.ps1'='restore'; 'Verify-KoreanPatch.ps1'='verify'; 'README_KO.txt'='readme'
    'payload/data_jp.dat'='payload'
}
$files = @()
foreach ($entry in $roles.GetEnumerator()) {
    $path = Join-Path $package ($entry.Key.Replace('/', '\'))
    $files += [ordered]@{path=$entry.Key;role=$entry.Value;size=(Get-Item -LiteralPath $path).Length;sha256=(Hash $path)}
}
$manifest = [ordered]@{
    schema='criminal-girls-invite-only.ko-patch.v1';patch_version='fixture';installed_to_game=$false
    game=[ordered]@{executable_relative_path='steam_criminal.exe';data_relative_path='data/data_jp.dat';baseline_size=$baseline.Length;baseline_sha256=$baselineHash;patched_size=$patched.Length;patched_sha256=$patchedHash}
    payload=[ordered]@{path='payload/data_jp.dat'};files=$files
}
Write-Utf8 (Join-Path $package 'manifest.json') (($manifest | ConvertTo-Json -Depth 10) + "`n")

$cases = New-Object Collections.Generic.List[object]
function Pass([string]$Name, [hashtable]$Details) { [void]$cases.Add([ordered]@{name=$Name;status='PASS';details=$Details}) }

# 1. Package verify + normal/idempotent install and restore.
$verify = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'Verify-KoreanPatch.ps1') 2>&1
Assert ($LASTEXITCODE -eq 0 -and ($verify -join "`n") -match 'PASS') 'mini package verification failed'
$game = New-Game '01 한글 game path' $baseline
$backup = Join-Path $workspaceFull '01 backup path'
$a = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
Assert ($a.Code -eq 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $patchedHash) 'normal install failed'
$b = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
Assert ($b.Code -eq 0 -and $b.Text -match 'already_installed') 'idempotent install failed'
$c = Invoke-Patch $package 'Restore-KoreanPatch.ps1' $game $backup
Assert ($c.Code -eq 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $baselineHash) 'normal restore failed'
$d = Invoke-Patch $package 'Restore-KoreanPatch.ps1' $game $backup
Assert ($d.Code -eq 0 -and $d.Text -match 'already_restored' -and (No-Temps $game)) 'idempotent restore failed'
Pass 'normal_and_idempotent' @{install=$a.Code;install_again=$b.Code;restore=$c.Code;restore_again=$d.Code}

# 2. Tampered payload rejected before backup or game write.
$tamperedPackage = Join-Path $workspaceFull 'tampered_package'
Copy-Item -LiteralPath $package -Destination $tamperedPackage -Recurse
Flip-FirstByte (Join-Path $tamperedPackage 'payload\data_jp.dat')
$game = New-Game '02 tampered payload game' $baseline
$backup = Join-Path $workspaceFull '02 backup'
$a = Invoke-Patch $tamperedPackage 'Install-KoreanPatch.ps1' $game $backup
Assert ($a.Code -ne 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $baselineHash -and -not (Test-Path -LiteralPath $backup)) 'tampered payload was not rejected pre-write'
Pass 'tampered_payload_rejected' @{exit_code=$a.Code;backup_created=(Test-Path -LiteralPath $backup)}

# 3. Tampered live baseline rejected before backup write.
$badData = [byte[]]$baseline.Clone(); $badData[0] = 1
$game = New-Game '03 tampered game' $badData
$backup = Join-Path $workspaceFull '03 backup'
$a = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
Assert ($a.Code -ne 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -ne $baselineHash -and -not (Test-Path -LiteralPath $backup)) 'tampered game was not rejected pre-write'
Pass 'tampered_game_rejected' @{exit_code=$a.Code;backup_created=(Test-Path -LiteralPath $backup)}

# 4. Tampered backup rejected while Korean file remains intact, then repaired restore succeeds.
$game = New-Game '04 tampered backup game' $baseline
$backup = Join-Path $workspaceFull '04 backup'
$a = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
Assert ($a.Code -eq 0) 'setup install for backup tamper failed'
$state = Get-Content -LiteralPath (Join-Path $backup 'CriminalGirlsInviteOnly-KoreanPatch\current.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Flip-FirstByte ([string]$state.backup_path)
$b = Invoke-Patch $package 'Restore-KoreanPatch.ps1' $game $backup
Assert ($b.Code -ne 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $patchedHash) 'tampered backup did not preserve Korean file'
[IO.File]::WriteAllBytes([string]$state.backup_path, $baseline)
$c = Invoke-Patch $package 'Restore-KoreanPatch.ps1' $game $backup
Assert ($c.Code -eq 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $baselineHash) 'restore after backup repair failed'
Pass 'tampered_backup_rejected' @{restore_exit=$b.Code;repaired_restore_exit=$c.Code}

# 5. Failure after replacement triggers verified rollback.
$game = New-Game '05 forced rollback game' $baseline
$backup = Join-Path $workspaceFull '05 backup'
$stateRoot = Join-Path $backup 'CriminalGirlsInviteOnly-KoreanPatch'
New-Item -ItemType Directory -Path (Join-Path $stateRoot 'current.json') -Force | Out-Null
$a = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
Assert ($a.Code -ne 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $baselineHash -and (No-Temps $game)) 'forced post-replace failure did not roll back'
$rolledBack = @(Get-ChildItem -LiteralPath (Join-Path $stateRoot 'transactions') -Recurse -File -Filter journal.json | ForEach-Object {(Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json).status}) -contains 'rolled_back'
Assert $rolledBack 'rollback journal missing'
Pass 'post_replace_failure_rollback' @{exit_code=$a.Code;journal_rolled_back=$rolledBack}

# 6. Simulated interruption after replacement is detected and recovered.
$game = New-Game '06 interruption game' $baseline
$backup = Join-Path $workspaceFull '06 backup'
$a = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
Assert ($a.Code -eq 0) 'interruption setup install failed'
$stateRoot = Join-Path $backup 'CriminalGirlsInviteOnly-KoreanPatch'
$current = Join-Path $stateRoot 'current.json'
$journalPath = (Get-ChildItem -LiteralPath (Join-Path $stateRoot 'transactions') -Recurse -File -Filter journal.json | Select-Object -First 1).FullName
$journal = Get-Content -LiteralPath $journalPath -Raw -Encoding UTF8 | ConvertFrom-Json
$journal.status = 'in_progress'
Write-Utf8 $journalPath (($journal | ConvertTo-Json -Depth 10) + "`n")
Remove-Item -LiteralPath $current -Force
$leftover = Join-Path (Join-Path $game 'data') ".cgko_incoming_$($journal.transaction_id).dat"
[IO.File]::WriteAllBytes($leftover, [byte[]](1,2,3))
$b = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
Assert ($b.Code -ne 0 -and $b.Text -match 'Recover-KoreanPatch') 'pending transaction was not detected'
$c = Invoke-Patch $package 'Recover-KoreanPatch.ps1' $game $backup
Assert ($c.Code -eq 0 -and $c.Text -match 'recovered_installed' -and (Test-Path -LiteralPath $current) -and -not (Test-Path -LiteralPath $leftover)) 'interrupted install recovery failed'
$d = Invoke-Patch $package 'Restore-KoreanPatch.ps1' $game $backup
Assert ($d.Code -eq 0 -and (Hash (Join-Path $game 'data\data_jp.dat')) -eq $baselineHash) 'post-recovery restore failed'
Pass 'interruption_recovery' @{pending_install_exit=$b.Code;recover_exit=$c.Code;restore_exit=$d.Code}

# 7. Same process name elsewhere is allowed; exact target path is blocked.
$other = Join-Path $workspaceFull '07 other process'
New-Item -ItemType Directory -Path $other -Force | Out-Null
Copy-Item -LiteralPath 'C:\Windows\System32\PING.EXE' -Destination (Join-Path $other 'steam_criminal.exe') -Force
$game = New-Game '07 process game' $baseline
$backup = Join-Path $workspaceFull '07 backup'
$process = Start-Process -FilePath (Join-Path $other 'steam_criminal.exe') -ArgumentList @('-t','127.0.0.1') -WindowStyle Hidden -PassThru
try {
    Start-Sleep -Milliseconds 700
    $a = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $backup
    Assert ($a.Code -eq 0) 'same-name process at another path incorrectly blocked install'
    $b = Invoke-Patch $package 'Restore-KoreanPatch.ps1' $game $backup
    Assert ($b.Code -eq 0) 'same-name process at another path incorrectly blocked restore'
} finally { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
$exactProcess = Start-Process -FilePath (Join-Path $game 'steam_criminal.exe') -ArgumentList @('-t','127.0.0.1') -WindowStyle Hidden -PassThru
try {
    Start-Sleep -Milliseconds 700
    $newBackup = Join-Path $workspaceFull '07 exact backup'
    $c = Invoke-Patch $package 'Install-KoreanPatch.ps1' $game $newBackup
    Assert ($c.Code -ne 0 -and $c.Text -match 'target game process is running' -and -not (Test-Path -LiteralPath $newBackup)) 'exact target process was not blocked pre-write'
} finally { Stop-Process -Id $exactProcess.Id -Force -ErrorAction SilentlyContinue }
Pass 'canonical_process_path' @{other_path_install=$a.Code;other_path_restore=$b.Code;exact_path_exit=$c.Code}

$tempCount = @(Get-ChildItem -LiteralPath $workspaceFull -Recurse -Force -File | Where-Object {$_.Name -like '.cgko_*'}).Count
Assert ($tempCount -eq 0) "fixture transaction files remain: $tempCount"
$payload = [ordered]@{
    status='PASS'; windows_powershell='5.1'; fixture_package=$package; case_count=$cases.Count
    cases=$cases; leftover_transaction_files=$tempCount
}
Write-Utf8 $Report (($payload | ConvertTo-Json -Depth 12) + "`n")
$payload | ConvertTo-Json -Depth 12
