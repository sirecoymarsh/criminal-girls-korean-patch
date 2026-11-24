[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$TargetPackage,
  [Parameter(Mandatory=$true)][string]$Report
)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Key($d){(@([string]$d.ThreatID,([datetime]$d.InitialDetectionTime).ToString('o'))+@($d.Resources|ForEach-Object{[string]$_}))-join'|'}
$target=[IO.Path]::GetFullPath($TargetPackage).TrimEnd('\')
if(-not(Test-Path -LiteralPath $target -PathType Container)){throw "Package not found: $target"}
$manifestPath=Join-Path $target 'manifest.json';$manifest=Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath|ConvertFrom-Json
$expected=@('manifest.json')+@($manifest.files|ForEach-Object{([string]$_.path).Replace('/','\')})
$files=@(Get-ChildItem -LiteralPath $target -Recurse -Force -File);$actual=@($files|ForEach-Object{$_.FullName.Substring($target.Length).TrimStart('\')})
$delta=@(($expected+$actual)|Group-Object|Where-Object{$_.Count-ne2}|ForEach-Object{$_.Name}|Sort-Object -Unique)
if($delta.Count-ne0-or$files.Count-ne9){throw 'Package allowlist mismatch'}
$before=[ordered]@{};foreach($rel in $expected){$p=Join-Path $target $rel;$before[$rel]=[ordered]@{size=(Get-Item -LiteralPath $p).Length;sha256=Hash $p}}
foreach($row in $manifest.files){$rel=([string]$row.path).Replace('/','\');if($before[$rel].size-ne[long]$row.size-or$before[$rel].sha256-ne([string]$row.sha256).ToLowerInvariant()){throw "Manifest mismatch: $rel"}}
$statusBefore=Get-MpComputerStatus;$pre=@(Get-MpThreatDetection -ErrorAction SilentlyContinue);$preKeys=@{};foreach($d in $pre){$preKeys[(Key $d)]=$true}
$platform=Get-ChildItem -LiteralPath 'C:\ProgramData\Microsoft\Windows Defender\Platform' -Directory|Sort-Object{[version](($_.Name-split'-')[0])}-Descending|Select-Object -First 1;$tool=Join-Path $platform.FullName 'MpCmdRun.exe'
$started=Get-Date;$old=$ErrorActionPreference;$ErrorActionPreference='Continue';try{$scanOutput=&$tool -Scan -ScanType 3 -File $target 2>&1;$code=$LASTEXITCODE}finally{$ErrorActionPreference=$old};$ended=Get-Date
$statusAfter=Get-MpComputerStatus;$post=@(Get-MpThreatDetection -ErrorAction SilentlyContinue);$new=@($post|Where-Object{-not$preKeys.ContainsKey((Key $_))});$targetDetections=@($post|Where-Object{@($_.Resources|ForEach-Object{[string]$_}|Where-Object{$_.IndexOf($target,[StringComparison]::OrdinalIgnoreCase)-ge0}).Count-gt0})
$unchanged=$true;foreach($rel in $expected){$p=Join-Path $target $rel;if(-not(Test-Path -LiteralPath $p)-or(Get-Item -LiteralPath $p).Length-ne$before[$rel].size-or(Hash $p)-ne$before[$rel].sha256){$unchanged=$false}}
$pass=$code-eq0-and$unchanged-and$targetDetections.Count-eq0
$result=[ordered]@{schema='criminal-girls.defender-extracted-package-scan.v9';status=if($pass){'PASS'}else{'FAIL'};target_package=$target;started_at=$started.ToString('o');ended_at=$ended.ToString('o');duration_seconds=[math]::Round(($ended-$started).TotalSeconds,3);scan_tool=$tool;scan_exit_code=$code;scan_output=@($scanOutput|ForEach-Object{$_.ToString()});file_count=$files.Count;manifest_sha256=Hash $manifestPath;target_unchanged=$unchanged;detections_before_total=$pre.Count;detections_after_total=$post.Count;new_detection_count=$new.Count;target_detection_count=$targetDetections.Count;defender=[ordered]@{am_service_enabled=[bool]$statusAfter.AMServiceEnabled;antivirus_enabled=[bool]$statusAfter.AntivirusEnabled;real_time_protection_enabled=[bool]$statusAfter.RealTimeProtectionEnabled;engine_version=[string]$statusAfter.AMEngineVersion;platform_version=[string]$statusAfter.AMProductVersion;signature_version=[string]$statusAfter.AntivirusSignatureVersion;signature_last_updated=([datetime]$statusAfter.AntivirusSignatureLastUpdated).ToString('o')}}
[IO.File]::WriteAllText($Report,(($result|ConvertTo-Json -Depth 12)+"`n"),(New-Object Text.UTF8Encoding($false)));$result|ConvertTo-Json -Depth 12;if(-not$pass){exit 1}
