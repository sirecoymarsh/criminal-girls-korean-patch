[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SourcePackage,
    [Parameter(Mandatory=$true)][string]$ScanCopy,
    [Parameter(Mandatory=$true)][string]$Report
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-Utf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}
function Detection-Key($Detection) {
    $resources = @($Detection.Resources | ForEach-Object { [string]$_ }) -join '|'
    return ('{0}|{1:o}|{2}' -f $Detection.ThreatID, $Detection.InitialDetectionTime, $resources)
}
function Detection-Summary($Detection) {
    [ordered]@{
        threat_id = [string]$Detection.ThreatID
        threat_status_id = [string]$Detection.ThreatStatusID
        initial_detection_time = if ($null -ne $Detection.InitialDetectionTime) { ([datetime]$Detection.InitialDetectionTime).ToString('o') } else { $null }
        last_threat_status_change_time = if ($null -ne $Detection.LastThreatStatusChangeTime) { ([datetime]$Detection.LastThreatStatusChangeTime).ToString('o') } else { $null }
        action_success = [bool]$Detection.ActionSuccess
        resources = @($Detection.Resources | ForEach-Object { [string]$_ })
    }
}

$source = [IO.Path]::GetFullPath($SourcePackage).TrimEnd('\')
$scan = [IO.Path]::GetFullPath($ScanCopy).TrimEnd('\')
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Source package not found: $source" }
$project = Split-Path -Parent (Split-Path -Parent $source)
$allowedParent = [IO.Path]::GetFullPath((Join-Path $project 'workspace')).TrimEnd('\') + '\'
if (-not $scan.StartsWith($allowedParent, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe scan-copy path: $scan" }
if ($source.StartsWith($scan + '\', [StringComparison]::OrdinalIgnoreCase) -or $scan.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase) -or $source -ieq $scan) { throw 'Source and scan copy overlap' }
if (Test-Path -LiteralPath $scan) { Remove-Item -LiteralPath $scan -Recurse -Force }
New-Item -ItemType Directory -Path $scan -Force | Out-Null

$sourceItems = @(Get-ChildItem -LiteralPath $source -Recurse -Force)
if (@($sourceItems | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count -ne 0) { throw 'Release package contains a reparse point' }
$sourceFiles = @($sourceItems | Where-Object { -not $_.PSIsContainer })
foreach ($file in $sourceFiles) {
    $rel = $file.FullName.Substring($source.Length).TrimStart('\')
    $dest = Join-Path $scan $rel
    $parent = Split-Path -Parent $dest
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    [IO.File]::Copy($file.FullName, $dest, $true)
}

$manifestPath = Join-Path $source 'manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expected = @('manifest.json') + @($manifest.files | ForEach-Object { ([string]$_.path).Replace('/', '\') })
$actual = @($sourceFiles | ForEach-Object { $_.FullName.Substring($source.Length).TrimStart('\') })
$missing = @($expected | Where-Object { $_ -notin $actual })
$unexpected = @($actual | Where-Object { $_ -notin $expected })
if ($missing.Count -ne 0 -or $unexpected.Count -ne 0 -or $expected.Count -ne $actual.Count) { throw "Package allowlist mismatch: missing=$($missing.Count), unexpected=$($unexpected.Count)" }

$sourceBefore = [ordered]@{}
$copyBefore = [ordered]@{}
foreach ($rel in ($expected | Sort-Object)) {
    $srcFile = Join-Path $source $rel
    $copyFile = Join-Path $scan $rel
    $sourceBefore[$rel] = [ordered]@{size=(Get-Item -LiteralPath $srcFile).Length;sha256=(Hash $srcFile)}
    $copyBefore[$rel] = [ordered]@{size=(Get-Item -LiteralPath $copyFile).Length;sha256=(Hash $copyFile)}
    if ($sourceBefore[$rel].size -ne $copyBefore[$rel].size -or $sourceBefore[$rel].sha256 -ne $copyBefore[$rel].sha256) { throw "Disposable copy mismatch: $rel" }
}
foreach ($entry in $manifest.files) {
    $rel = ([string]$entry.path).Replace('/', '\')
    if ($sourceBefore[$rel].size -ne [long]$entry.size -or $sourceBefore[$rel].sha256 -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "Manifest mismatch before scan: $rel" }
}

$statusBefore = Get-MpComputerStatus
$pre = @(Get-MpThreatDetection -ErrorAction SilentlyContinue)
$preKeys = @{}
foreach ($item in $pre) { $preKeys[(Detection-Key $item)] = $true }
$platformDir = Get-ChildItem -LiteralPath 'C:\ProgramData\Microsoft\Windows Defender\Platform' -Directory | Sort-Object { [version](($_.Name -split '-')[0]) } -Descending | Select-Object -First 1
$mpCmdRun = Join-Path $platformDir.FullName 'MpCmdRun.exe'
if (-not (Test-Path -LiteralPath $mpCmdRun)) { throw 'MpCmdRun.exe not found' }

$started = Get-Date
$oldPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $scanOutput = & $mpCmdRun -Scan -ScanType 3 -File $scan 2>&1
    $scanExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $oldPreference
}
$ended = Get-Date
$statusAfter = Get-MpComputerStatus
$post = @(Get-MpThreatDetection -ErrorAction SilentlyContinue)
$newDetections = @($post | Where-Object { -not $preKeys.ContainsKey((Detection-Key $_)) })
$scanDetections = @($post | Where-Object {
    $resources = @($_.Resources | ForEach-Object { [string]$_ })
    @($resources | Where-Object { $_.IndexOf($scan, [StringComparison]::OrdinalIgnoreCase) -ge 0 }).Count -gt 0
})

$sourceUnchanged = $true
$copyUnchanged = $true
foreach ($rel in $expected) {
    $srcFile = Join-Path $source $rel
    $copyFile = Join-Path $scan $rel
    if (-not (Test-Path -LiteralPath $srcFile) -or (Get-Item -LiteralPath $srcFile).Length -ne $sourceBefore[$rel].size -or (Hash $srcFile) -ne $sourceBefore[$rel].sha256) { $sourceUnchanged = $false }
    if (-not (Test-Path -LiteralPath $copyFile) -or (Get-Item -LiteralPath $copyFile).Length -ne $copyBefore[$rel].size -or (Hash $copyFile) -ne $copyBefore[$rel].sha256) { $copyUnchanged = $false }
}
$pass = ($scanExitCode -eq 0 -and $sourceUnchanged -and $copyUnchanged -and $scanDetections.Count -eq 0)
$result = [ordered]@{
    status = if ($pass) { 'PASS' } else { 'FAIL' }
    source_package = $source
    disposable_scan_copy = $scan
    started_at = $started.ToString('o')
    ended_at = $ended.ToString('o')
    duration_seconds = [math]::Round(($ended - $started).TotalSeconds, 3)
    scan_tool = $mpCmdRun
    scan_exit_code = $scanExitCode
    scan_output = @($scanOutput | ForEach-Object { $_.ToString() })
    file_count = $expected.Count
    manifest_sha256 = Hash $manifestPath
    payload_sha256 = ([string]$manifest.game.patched_sha256).ToLowerInvariant()
    source_unchanged = $sourceUnchanged
    disposable_copy_unchanged = $copyUnchanged
    detections_before_total = $pre.Count
    detections_after_total = $post.Count
    new_detection_count = $newDetections.Count
    scan_target_detection_count = $scanDetections.Count
    new_detections = @($newDetections | ForEach-Object { Detection-Summary $_ })
    scan_target_detections = @($scanDetections | ForEach-Object { Detection-Summary $_ })
    defender = [ordered]@{
        am_service_enabled = [bool]$statusAfter.AMServiceEnabled
        antivirus_enabled = [bool]$statusAfter.AntivirusEnabled
        real_time_protection_enabled = [bool]$statusAfter.RealTimeProtectionEnabled
        engine_version = [string]$statusAfter.AMEngineVersion
        platform_version = [string]$statusAfter.AMProductVersion
        signature_version = [string]$statusAfter.AntivirusSignatureVersion
        signature_last_updated = ([datetime]$statusAfter.AntivirusSignatureLastUpdated).ToString('o')
    }
}
Write-Utf8 $Report (($result | ConvertTo-Json -Depth 12) + "`n")
$result | ConvertTo-Json -Depth 12
if (-not $pass) { exit 1 }