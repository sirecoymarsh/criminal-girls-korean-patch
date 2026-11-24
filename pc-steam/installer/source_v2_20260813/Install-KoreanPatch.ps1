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

if ($live.overall -eq 'korean') {
    if (-not (Test-Path -LiteralPath $currentState -PathType Leaf)) {
        throw 'Korean files found but no verified install state exists. Restoration provenance is unavailable.'
    }
    $state = Read-Utf8Json $currentState
    if ($state.status -ne 'installed' -or
        -not [string]::Equals((Get-CanonicalPath ([string]$state.game_root)), $gameRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Korean files found but the recorded install state is invalid.'
    }
    $stateTargets = @{}
    foreach ($entry in @($state.targets)) { $stateTargets[[string]$entry.id] = $entry }
    foreach ($target in $targets) {
        if (-not $stateTargets.ContainsKey($target.Id)) { throw "Missing backup state for $($target.Id)" }
        $backup = Get-CanonicalPath ([string]$stateTargets[$target.Id].backup_path)
        $backupTree = Join-Path $stateRoot 'backups'
        if (-not (Test-IsSameOrChildPath $backup $backupTree) -or
            -not (Test-Path -LiteralPath $backup -PathType Leaf) -or
            (Get-Sha256 $backup) -ne $target.BaselineHash) {
            throw "Invalid recorded backup for $($target.Id)"
        }
    }
    Write-Result @{status='already_installed'; game_root=$gameRoot; game_state=$live.overall; targets=$live.targets}
    exit 0
}
if ($live.overall -ne 'original') {
    throw "Install requires both exact original files. Current state: $($live.overall). Use Recover-KoreanPatch.ps1 only for a recorded interrupted transaction."
}

$transactionId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [Guid]::NewGuid().ToString('N')
$transactionRoot = Join-Path $stateRoot (Join-Path 'transactions' $transactionId)
$backupDir = Join-Path $stateRoot (Join-Path 'backups' $transactionId)
$journalPath = Join-Path $transactionRoot 'journal.json'
New-Item -ItemType Directory -Path $transactionRoot,$backupDir -Force | Out-Null

$journalTargets = @()
foreach ($target in $targets) {
    $backup = Get-CanonicalPath (Join-Path $backupDir $target.BackupName)
    Copy-AndVerify $target.TargetPath $backup $target.BaselineHash
    $journalTargets += [pscustomobject][ordered]@{
        id=$target.Id
        target_path=$target.TargetPath
        payload_path=$target.PayloadPath
        backup_path=$backup
        baseline_size=$target.BaselineSize
        baseline_sha256=$target.BaselineHash
        patched_size=$target.PatchedSize
        patched_sha256=$target.PatchedHash
        status='backed_up'
    }
}

$journal = [ordered]@{
    schema='criminal-girls-ko-install-state.v2'
    status='in_progress'
    transaction_id=$transactionId
    game_root=$gameRoot
    targets=$journalTargets
    started_at=(Get-Date).ToString('o')
}
Write-Utf8JsonAtomic $journalPath $journal

try {
    foreach ($target in $targets) {
        Set-TargetFromSource $target $target.PayloadPath $target.PatchedHash $transactionId 'install'
        foreach ($entry in $journalTargets) {
            if ($entry.id -eq $target.Id) { $entry.status = 'installed' }
        }
        Write-Utf8JsonAtomic $journalPath $journal
    }
    $after = Get-TargetsState $targets
    if ($after.overall -ne 'korean') { throw "Post-install state is not fully Korean: $($after.overall)" }
    $journal.status = 'installed'
    $journal.completed_at = (Get-Date).ToString('o')
    Write-Utf8JsonAtomic $journalPath $journal
    Write-Utf8JsonAtomic $currentState $journal
    Remove-TransactionTemps $targets $transactionId
    Write-Result @{status='installed'; game_root=$gameRoot; game_state=$after.overall; targets=$after.targets; transaction_id=$transactionId; backup_dir=$backupDir}
} catch {
    $failure = $_.Exception.Message
    try {
        foreach ($target in $targets) {
            $entry = @($journalTargets | Where-Object { $_.id -eq $target.Id })[0]
            if (-not (Test-Path -LiteralPath $entry.backup_path -PathType Leaf) -or
                (Get-Sha256 $entry.backup_path) -ne $target.BaselineHash) {
                throw "Verified external backup unavailable for $($target.Id)"
            }
            $itemState = @(Get-TargetsState @($target)).targets[0]
            if ($itemState.state -ne 'original') {
                Set-TargetFromSource $target ([string]$entry.backup_path) $target.BaselineHash $transactionId 'rollback'
            }
        }
        $rolledBack = Get-TargetsState $targets
        if ($rolledBack.overall -ne 'original') { throw "Rollback verification failed: $($rolledBack.overall)" }
        $journal.status = 'rolled_back'
        $journal.failure = $failure
        $journal.completed_at = (Get-Date).ToString('o')
        Write-Utf8JsonAtomic $journalPath $journal
        Remove-TransactionTemps $targets $transactionId
    } catch {
        $rollbackFailure = $_.Exception.Message
        $journal.status = 'rollback_failed'
        $journal.failure = $failure
        $journal.rollback_failure = $rollbackFailure
        try { Write-Utf8JsonAtomic $journalPath $journal } catch {}
        throw "Install failed and rollback failed. Recovery journal: $journalPath"
    }
    throw "Install failed and both original files were restored: $failure"
}
