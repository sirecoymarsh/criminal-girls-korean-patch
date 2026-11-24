[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][ValidateSet('file','zip')][string]$Kind,
    [Parameter(Mandatory=$true)][string]$Report
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function DetectionKey($Detection){
  $resources=@($Detection.Resources|ForEach-Object{[string]$_})-join '|'
  '{0}|{1:o}|{2}' -f $Detection.ThreatID,$Detection.InitialDetectionTime,$resources
}
function DetectionSummary($Detection){
  [ordered]@{
    threat_id=[string]$Detection.ThreatID
    threat_status_id=[string]$Detection.ThreatStatusID
    initial_detection_time=if($null-ne$Detection.InitialDetectionTime){([datetime]$Detection.InitialDetectionTime).ToString('o')}else{$null}
    resources=@($Detection.Resources|ForEach-Object{[string]$_})
  }
}
$target=[IO.Path]::GetFullPath($Target)
if(-not(Test-Path -LiteralPath $target -PathType Leaf)){throw "Target not found: $target"}
$size=(Get-Item -LiteralPath $target).Length
$beforeHash=Hash $target
$statusBefore=Get-MpComputerStatus
$pre=@(Get-MpThreatDetection -ErrorAction SilentlyContinue)
$preKeys=@{};foreach($item in $pre){$preKeys[(DetectionKey $item)]=$true}
$platform=Get-ChildItem -LiteralPath 'C:\ProgramData\Microsoft\Windows Defender\Platform' -Directory|Sort-Object{[version](($_.Name-split'-')[0])}-Descending|Select-Object -First 1
$tool=Join-Path $platform.FullName 'MpCmdRun.exe'
if(-not(Test-Path -LiteralPath $tool)){throw 'MpCmdRun.exe not found'}
$started=Get-Date;$old=$ErrorActionPreference;$ErrorActionPreference='Continue'
try{$scanOutput=& $tool -Scan -ScanType 3 -File $target 2>&1;$code=$LASTEXITCODE}finally{$ErrorActionPreference=$old}
$ended=Get-Date;$statusAfter=Get-MpComputerStatus
$post=@(Get-MpThreatDetection -ErrorAction SilentlyContinue)
$new=@($post|Where-Object{-not$preKeys.ContainsKey((DetectionKey $_))})
$targetDetections=@($post|Where-Object{@($_.Resources|ForEach-Object{[string]$_}|Where-Object{$_.IndexOf($target,[StringComparison]::OrdinalIgnoreCase)-ge0}).Count-gt0})
$unchanged=(Test-Path -LiteralPath $target)-and(Get-Item -LiteralPath $target).Length-eq$size-and(Hash $target)-eq$beforeHash
$pass=$code-eq0-and$unchanged-and$targetDetections.Count-eq0
$schema=if($Kind-eq'zip'){'criminal-girls.defender-zip-scan.v9'}else{'criminal-girls.defender-file-scan.v9'}
$result=[ordered]@{
  schema=$schema;status=if($pass){'PASS'}else{'FAIL'};kind=$Kind;target=$target;size=$size;file_count=1;sha256=$beforeHash
  started_at=$started.ToString('o');ended_at=$ended.ToString('o');duration_seconds=[math]::Round(($ended-$started).TotalSeconds,3)
  scan_tool=$tool;scan_exit_code=$code;scan_output=@($scanOutput|ForEach-Object{$_.ToString()})
  detections_before_total=$pre.Count;detections_after_total=$post.Count;new_detection_count=$new.Count;target_detection_count=$targetDetections.Count
  target_unchanged=$unchanged;new_detections=@($new|ForEach-Object{DetectionSummary $_});target_detections=@($targetDetections|ForEach-Object{DetectionSummary $_})
  defender=[ordered]@{am_service_enabled=[bool]$statusAfter.AMServiceEnabled;antivirus_enabled=[bool]$statusAfter.AntivirusEnabled;real_time_protection_enabled=[bool]$statusAfter.RealTimeProtectionEnabled;engine_version=[string]$statusAfter.AMEngineVersion;platform_version=[string]$statusAfter.AMProductVersion;signature_version=[string]$statusAfter.AntivirusSignatureVersion;signature_last_updated=([datetime]$statusAfter.AntivirusSignatureLastUpdated).ToString('o')}
}
$parent=Split-Path -Parent $Report;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent -Force|Out-Null}
[IO.File]::WriteAllText($Report,(($result|ConvertTo-Json -Depth 12)+"`n"),(New-Object Text.UTF8Encoding($false)))
$result|ConvertTo-Json -Depth 12
if(-not$pass){exit 1}
