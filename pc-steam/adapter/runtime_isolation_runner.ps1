param([Parameter(Mandatory=$true)][string]$Fixture,[Parameter(Mandatory=$true)][string]$Report,[int]$Seconds=90,[string]$Label='isolation')
$ErrorActionPreference='Stop'
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class CGIsolationHide { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd,int nCmdShow); }
"@
$exe=Join-Path $Fixture 'steam_criminal.exe'
$started=Get-Date
$proc=Start-Process -FilePath $exe -WorkingDirectory $Fixture -WindowStyle Minimized -PassThru
$states=@();$survived=$false;$code=$null
try {
 for($s=0;$s -le $Seconds;$s+=5){
  if($s){Start-Sleep -Seconds 5}
  $live=Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
  if(-not $live){$code=$null;$states+=@([ordered]@{second=$s;alive=$false;exit_code=$null});break}
  if($live.MainWindowHandle -ne 0){[CGIsolationHide]::ShowWindow($live.MainWindowHandle,6)|Out-Null}
  $states+=@([ordered]@{second=$s;alive=$true;window=($live.MainWindowHandle.ToInt64())})
 }
 $survived=[bool](Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)
 $result=[ordered]@{label=$Label;fixture=$Fixture;exe_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $exe).Hash.ToLowerInvariant();data_jp_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Fixture 'data\data_jp.dat')).Hash.ToLowerInvariant();started=$started.ToString('o');seconds=$Seconds;survived=$survived;exit_code=$code;states=$states;status=if($survived){'PASS'}else{'FAIL'}}
 [IO.File]::WriteAllText($Report,($result|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
} finally {
 $live=Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
 if($live){Stop-Process -Id $proc.Id -Force}
}

