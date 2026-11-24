[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$GameRoot,
    [Parameter(Mandatory=$true)][string]$BackupRoot
)

. (Join-Path $PSScriptRoot 'PatchCommon.ps1')

$packageRoot = Get-CanonicalPath $PSScriptRoot
$gameRoot = Get-CanonicalPath $GameRoot
$backupBase = Get-CanonicalPath $BackupRoot
$manifest = Get-PackageManifest $packageRoot
Assert-PackageIntegrity $packageRoot $manifest
Assert-SeparateTrees $gameRoot $packageRoot $backupBase
Assert-NoReparseAncestor $gameRoot
Assert-NoReparseAncestor $backupBase
Assert-TargetProcessStopped $gameRoot ([string]$manifest.game.executable_relative_path)

$targets = @(Get-ManifestTargets $manifest $gameRoot $packageRoot)
$targetById = @{}
foreach ($target in $targets) { $targetById[$target.Id] = $target }
$stateRoot = Join-Path $backupBase 'CriminalGirlsInviteOnly-KoreanPatch-v2'
$currentState = Join-Path $stateRoot 'current.json'
$pending = @(Get-PendingJournals $stateRoot $gameRoot)
if ($pending.Count -eq 0) {
    $live = Get-TargetsState $targets
    Write-Result @{status='nothing_to_recover'; game_root=$gameRoot; game_state=$live.overall; targets=$live.targets}
    exit 0
}
if ($pending.Count -gt 1) { throw "Multiple interrupted transactions require manual inspection under: $stateRoot" }

$record = $pending[0]
$journal = $record.Journal
$journalPath = $record.Path
$transactionId = [string]$journal.transaction_id
$journalTargets = @($journal.targets)
if ($journalTargets.Count -ne $targets.Count) { throw 'Interrupted journal target count mismatch.' }
$journalById = @{}
foreach ($entry in $journalTargets) { $journalById[[string]$entry.id] = $entry }
foreach ($target in $targets) {
    if (-not $journalById.ContainsKey($target.Id)) { throw "Interrupted journal missing target $($target.Id)" }
}
$live = Get-TargetsState $targets

if ($journal.status -eq 'in_progress') {
    foreach ($target in $targets) {
        $entry = $journalById[$target.Id]
        $backup = Get-CanonicalPath ([string]$entry.backup_path)
        if (-not (Test-IsSameOrChildPath $backup (Join-Path $stateRoot 'backups')) -or
            -not (Test-Path -LiteralPath $backup -PathType Leaf) -or
            (Get-Sha256 $backup) -ne $target.BaselineHash) {
            throw "Interrupted install backup is missing or invalid for $($target.Id)"
        }
    }
    if ($live.overall -eq 'korean') {
        $journal.status = 'installed'
        $journal | Add-Member -NotePropertyName recovered_at -NotePropertyValue ((Get-Date).ToString('o')) -Force
        Write-Utf8JsonAtomic $journalPath $journal
        Write-Utf8JsonAtomic $currentState $journal
        $resultStatus = 'recovered_installed'
    } else {
        foreach ($target in $targets) {
            $entry = $journalById[$target.Id]
            $itemState = @(Get-TargetsState @($target)).targets[0]
            if ($itemState.state -ne 'original') {
                Set-TargetFromSource $target ([string]$entry.backup_path) $target.BaselineHash $transactionId 'recover_install'
            }
        }
        $after = Get-TargetsState $targets
        if ($after.overall -ne 'original') { throw "Install recovery could not restore originals: $($after.overall)" }
        $journal.status = 'rolled_back'
        $journal | Add-Member -NotePropertyName recovered_at -NotePropertyValue ((Get-Date).ToString('o')) -Force
        Write-Utf8JsonAtomic $journalPath $journal
        $resultStatus = 'recovered_original'
    }
} elseif ($journal.status -eq 'restore_in_progress') {
    foreach ($target in $targets) {
        $entry = $journalById[$target.Id]
        $backup = Get-CanonicalPath ([string]$entry.backup_path)
        if (-not (Test-IsSameOrChildPath $backup (Join-Path $stateRoot 'backups')) -or
            -not (Test-Path -LiteralPath $backup -PathType Leaf) -or
            (Get-Sha256 $backup) -ne $target.BaselineHash) {
            throw "Interrupted restore backup is missing or invalid for $($target.Id)"
        }
    }
    if ($live.overall -ne 'original') {
        foreach ($target in $targets) {
            $entry = $journalById[$target.Id]
            $itemState = @(Get-TargetsState @($target)).targets[0]
            if ($itemState.state -ne 'original') {
                Set-TargetFromSource $target ([string]$entry.backup_path) $target.BaselineHash $transactionId 'recover_restore'
            }
        }
    }
    $after = Get-TargetsState $targets
    if ($after.overall -ne 'original') { throw "Restore recovery could not finish originals: $($after.overall)" }
    $journal.status = 'restored'
    $journal | Add-Member -NotePropertyName recovered_at -NotePropertyValue ((Get-Date).ToString('o')) -Force
    Write-Utf8JsonAtomic $journalPath $journal
    if (Test-Path -LiteralPath $currentState -PathType Leaf) {
        $state = Read-Utf8Json $currentState
        $state.status = 'restored'
        $state | Add-Member -NotePropertyName recovered_at -NotePropertyValue ((Get-Date).ToString('o')) -Force
        Write-Utf8JsonAtomic $currentState $state
    }
    $resultStatus = 'recovered_restored'
} else {
    throw "Unsupported recovery state: $($journal.status)"
}

Remove-TransactionTemps $targets $transactionId
$final = Get-TargetsState $targets
Write-Result @{status=$resultStatus; game_root=$gameRoot; game_state=$final.overall; targets=$final.targets; journal=$journalPath}
