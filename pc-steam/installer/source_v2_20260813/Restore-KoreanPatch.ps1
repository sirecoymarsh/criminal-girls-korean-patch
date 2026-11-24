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
$stateRoot = Join-Path $backupBase 'CriminalGirlsInviteOnly-KoreanPatch-v2'
$currentState = Join-Path $stateRoot 'current.json'
Assert-NoPendingTransactions $stateRoot $gameRoot
$live = Get-TargetsState $targets
if ($live.overall -eq 'original') {
    Write-Result @{status='already_restored'; game_root=$gameRoot; game_state=$live.overall; targets=$live.targets}
    exit 0
}
if ($live.overall -ne 'korean') { throw "Restore requires both exact Korean files. Current state: $($live.overall)" }
if (-not (Test-Path -LiteralPath $currentState -PathType Leaf)) { throw 'Install state is missing.' }

$installedState = Read-Utf8Json $currentState
if ($installedState.status -ne 'installed') { throw "Install state is not restorable: $($installedState.status)" }
if (-not [string]::Equals((Get-CanonicalPath ([string]$installedState.game_root)), $gameRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Install state belongs to another game path.'
}
$stateTargets = @{}
foreach ($entry in @($installedState.targets)) { $stateTargets[[string]$entry.id] = $entry }
$journalTargets = @()
foreach ($target in $targets) {
    if (-not $stateTargets.ContainsKey($target.Id)) { throw "Missing backup state for $($target.Id)" }
    $backup = Get-CanonicalPath ([string]$stateTargets[$target.Id].backup_path)
    $backupTree = Join-Path $stateRoot 'backups'
    if (-not (Test-IsSameOrChildPath $backup $backupTree) -or
        -not (Test-Path -LiteralPath $backup -PathType Leaf) -or
        (Get-Sha256 $backup) -ne $target.BaselineHash) {
        throw "Backup file is missing or invalid for $($target.Id)"
    }
    $journalTargets += [pscustomobject][ordered]@{
        id=$target.Id
        target_path=$target.TargetPath
        payload_path=$target.PayloadPath
        backup_path=$backup
        baseline_size=$target.BaselineSize
        baseline_sha256=$target.BaselineHash
        patched_size=$target.PatchedSize
        patched_sha256=$target.PatchedHash
        status='pending_restore'
    }
}

$transactionId = 'restore_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [Guid]::NewGuid().ToString('N')
$journalPath = Join-Path $stateRoot (Join-Path 'transactions' (Join-Path $transactionId 'journal.json'))
$journal = [ordered]@{
    schema='criminal-girls-ko-restore-state.v2'
    status='restore_in_progress'
    transaction_id=$transactionId
    game_root=$gameRoot
    targets=$journalTargets
    started_at=(Get-Date).ToString('o')
}
Write-Utf8JsonAtomic $journalPath $journal

try {
    foreach ($target in $targets) {
        $entry = @($journalTargets | Where-Object { $_.id -eq $target.Id })[0]
        Set-TargetFromSource $target ([string]$entry.backup_path) $target.BaselineHash $transactionId 'restore'
        $entry.status = 'restored'
        Write-Utf8JsonAtomic $journalPath $journal
    }
    $after = Get-TargetsState $targets
    if ($after.overall -ne 'original') { throw "Post-restore state is not fully original: $($after.overall)" }
    $journal.status = 'restored'
    $journal.completed_at = (Get-Date).ToString('o')
    Write-Utf8JsonAtomic $journalPath $journal
    $installedState.status = 'restored'
    $installedState | Add-Member -NotePropertyName restored_at -NotePropertyValue ((Get-Date).ToString('o')) -Force
    Write-Utf8JsonAtomic $currentState $installedState
    Remove-TransactionTemps $targets $transactionId
    Write-Result @{status='restored'; game_root=$gameRoot; game_state=$after.overall; targets=$after.targets; transaction_id=$transactionId}
} catch {
    $failure = $_.Exception.Message
    try {
        foreach ($target in $targets) {
            $itemState = @(Get-TargetsState @($target)).targets[0]
            if ($itemState.state -ne 'korean') {
                Set-TargetFromSource $target $target.PayloadPath $target.PatchedHash $transactionId 'restore_rollback'
            }
        }
        $retained = Get-TargetsState $targets
        if ($retained.overall -ne 'korean') { throw "Restore rollback verification failed: $($retained.overall)" }
        $journal.status = 'restore_rolled_back'
        $journal.failure = $failure
        $journal.completed_at = (Get-Date).ToString('o')
        Write-Utf8JsonAtomic $journalPath $journal
        Remove-TransactionTemps $targets $transactionId
    } catch {
        $rollbackFailure = $_.Exception.Message
        $journal.status = 'restore_rollback_failed'
        $journal.failure = $failure
        $journal.rollback_failure = $rollbackFailure
        try { Write-Utf8JsonAtomic $journalPath $journal } catch {}
        throw "Restore failed and rollback failed. Recovery journal: $journalPath"
    }
    throw "Restore failed and both Korean files were retained: $failure"
}
