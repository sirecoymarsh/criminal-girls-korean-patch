[CmdletBinding()]
param([string]$GameRoot = '')

. (Join-Path $PSScriptRoot 'PatchCommon.ps1')

$packageRoot = Get-CanonicalPath $PSScriptRoot
$manifest = Get-PackageManifest $packageRoot
Assert-PackageIntegrity $packageRoot $manifest
$manifestTargets = @(Get-ManifestTargets $manifest '' $packageRoot)
$result = [ordered]@{
    status='PASS'
    package=$packageRoot
    package_state='verified'
    targets=@($manifestTargets | ForEach-Object {
        [pscustomobject][ordered]@{
            id=$_.Id
            payload_path=$_.PayloadPath
            payload_size=(Get-Item -LiteralPath $_.PayloadPath).Length
            payload_sha256=(Get-Sha256 $_.PayloadPath)
        }
    })
}
if ($GameRoot) {
    $game = Get-CanonicalPath $GameRoot
    Assert-NoReparseAncestor $game
    $targets = @(Get-ManifestTargets $manifest $game $packageRoot)
    $state = Get-TargetsState $targets
    $result.game_root = $game
    $result.game_state = $state.overall
    $result.game_targets = $state.targets
    if ($state.overall -in @('unsupported','mixed')) { $result.status = 'FAIL' }
}
Write-Output ($result | ConvertTo-Json -Depth 16)
if ($result.status -ne 'PASS') { exit 1 }
