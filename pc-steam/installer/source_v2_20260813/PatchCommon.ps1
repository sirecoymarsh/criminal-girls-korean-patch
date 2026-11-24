Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-CanonicalPath {
    param([Parameter(Mandatory=$true)][string]$Path)
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if (-not [IO.Path]::IsPathRooted($expanded)) {
        $expanded = Join-Path (Get-Location).Path $expanded
    }
    $full = [IO.Path]::GetFullPath($expanded)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) {
        $full = $full.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    }
    return $full
}

function Test-IsSameOrChildPath {
    param([string]$Child, [string]$Parent)
    $c = Get-CanonicalPath $Child
    $p = Get-CanonicalPath $Parent
    if ([string]::Equals($c, $p, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    $prefix = $p
    if (-not $prefix.EndsWith([IO.Path]::DirectorySeparatorChar)) {
        $prefix += [IO.Path]::DirectorySeparatorChar
    }
    return $c.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-SeparateTrees {
    param([string]$GameRoot, [string]$PackageRoot, [string]$BackupRoot)
    $pairs = @(
        @($GameRoot, $PackageRoot, 'game/package'),
        @($GameRoot, $BackupRoot, 'game/backup'),
        @($PackageRoot, $BackupRoot, 'package/backup')
    )
    foreach ($pair in $pairs) {
        if ((Test-IsSameOrChildPath $pair[0] $pair[1]) -or (Test-IsSameOrChildPath $pair[1] $pair[0])) {
            throw "Overlapping path trees are not allowed: $($pair[2])"
        }
    }
}

function Assert-NoReparseAncestor {
    param([Parameter(Mandatory=$true)][string]$Path)
    $probe = Get-CanonicalPath $Path
    while (-not (Test-Path -LiteralPath $probe)) {
        $parent = Split-Path -Parent $probe
        if (-not $parent -or $parent -eq $probe) { break }
        $probe = $parent
    }
    while ($probe -and (Test-Path -LiteralPath $probe)) {
        $item = Get-Item -LiteralPath $probe -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse-point ancestry is not allowed: $probe"
        }
        $parent = Split-Path -Parent $probe
        if (-not $parent -or $parent -eq $probe) { break }
        $probe = $parent
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory=$true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-Utf8Json {
    param([Parameter(Mandatory=$true)][string]$Path)
    $utf8 = New-Object Text.UTF8Encoding($false)
    return ([IO.File]::ReadAllText($Path, $utf8) | ConvertFrom-Json)
}

function Write-Utf8JsonAtomic {
    param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)]$Value)
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $temp = "$Path.tmp.$([Guid]::NewGuid().ToString('N'))"
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($temp, ($Value | ConvertTo-Json -Depth 12), $utf8)
    if (Test-Path -LiteralPath $Path) {
        $old = "$Path.old.$([Guid]::NewGuid().ToString('N'))"
        [IO.File]::Replace($temp, $Path, $old, $true)
        Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
    } else {
        [IO.File]::Move($temp, $Path)
    }
}

function Get-PackageManifest {
    param([Parameter(Mandatory=$true)][string]$PackageRoot)
    $manifestPath = Join-Path $PackageRoot 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Missing manifest: $manifestPath" }
    return Read-Utf8Json $manifestPath
}

function Assert-PackageIntegrity {
    param([Parameter(Mandatory=$true)][string]$PackageRoot, [Parameter(Mandatory=$true)]$Manifest)
    $package = Get-CanonicalPath $PackageRoot
    Assert-NoReparseAncestor $package
    $expected = @('manifest.json')
    foreach ($file in @($Manifest.files)) {
        $rel = ([string]$file.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
        $full = Get-CanonicalPath (Join-Path $package $rel)
        if (-not (Test-IsSameOrChildPath $full $package)) { throw "Package path escapes root: $rel" }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Missing package file: $rel" }
        $item = Get-Item -LiteralPath $full -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Package reparse point rejected: $rel" }
        if ($item.Length -ne [int64]$file.size) { throw "Package size mismatch: $rel" }
        if ((Get-Sha256 $full) -ne ([string]$file.sha256).ToLowerInvariant()) { throw "Package hash mismatch: $rel" }
        $expected += ([string]$file.path).Replace('\','/')
    }
    $actual = @(Get-ChildItem -LiteralPath $package -Recurse -File -Force | ForEach-Object {
        $_.FullName.Substring($package.Length).TrimStart('\','/').Replace('\','/')
    })
    $delta = @(Compare-Object -ReferenceObject @($expected | Sort-Object -Unique) -DifferenceObject @($actual | Sort-Object -Unique))
    if ($delta.Count -ne 0) { throw "Package allowlist mismatch: $($delta | Out-String)" }
}

function Assert-TargetProcessStopped {
    param([string]$GameRoot, [string]$ExecutableRelativePath)
    $wanted = Get-CanonicalPath (Join-Path $GameRoot $ExecutableRelativePath)
    $name = [IO.Path]::GetFileName($wanted).Replace("'", "''")
    $processes = @()
    try {
        $processes = @(Get-CimInstance Win32_Process -Filter "Name='$name'" -ErrorAction Stop)
    } catch {
        $processes = @(Get-WmiObject Win32_Process -Filter "Name='$name'" -ErrorAction SilentlyContinue)
    }
    foreach ($process in $processes) {
        if (-not $process.ExecutablePath) { continue }
        try { $actual = Get-CanonicalPath ([string]$process.ExecutablePath) } catch { continue }
        if ([string]::Equals($actual, $wanted, [StringComparison]::OrdinalIgnoreCase)) {
            throw "The target game process is running (PID $($process.ProcessId)): $actual"
        }
    }
}

function Get-PendingJournals {
    param([string]$StateRoot, [string]$GameRoot)
    $result = @()
    $transactions = Join-Path $StateRoot 'transactions'
    if (-not (Test-Path -LiteralPath $transactions -PathType Container)) { return @() }
    foreach ($path in @(Get-ChildItem -LiteralPath $transactions -Recurse -File -Filter 'journal.json' -ErrorAction SilentlyContinue)) {
        try { $journal = Read-Utf8Json $path.FullName } catch { continue }
        if ($journal.status -notin @('in_progress','restore_in_progress')) { continue }
        try { $recordedGame = Get-CanonicalPath ([string]$journal.game_root) } catch { continue }
        if ([string]::Equals($recordedGame, (Get-CanonicalPath $GameRoot), [StringComparison]::OrdinalIgnoreCase)) {
            $result += [pscustomobject]@{Path=$path.FullName; Journal=$journal}
        }
    }
    return @($result)
}

function Assert-NoPendingTransactions {
    param([string]$StateRoot, [string]$GameRoot)
    $pending = @(Get-PendingJournals $StateRoot $GameRoot)
    if ($pending.Count -gt 0) {
        throw "An interrupted transaction requires Recover-KoreanPatch.ps1: $($pending[0].Path)"
    }
}

function Copy-AndVerify {
    param([string]$Source, [string]$Destination, [string]$ExpectedHash)
    [IO.File]::Copy($Source, $Destination, $true)
    if ((Get-Sha256 $Destination) -ne $ExpectedHash.ToLowerInvariant()) {
        Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
        throw "Copied file hash mismatch: $Destination"
    }
}

function Write-Result {
    param([hashtable]$Value)
    Write-Output ($Value | ConvertTo-Json -Depth 10)
}


# v2 multi-target overrides and helpers.
function Get-PackageManifest {
    param([Parameter(Mandatory=$true)][string]$PackageRoot)
    $manifestPath = Join-Path $PackageRoot 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Missing manifest: $manifestPath" }
    $manifest = Read-Utf8Json $manifestPath
    if ([string]$manifest.schema -ne 'criminal-girls-invite-only.ko-patch.v2') {
        throw "Unsupported manifest schema: $($manifest.schema)"
    }
    if (@($manifest.game.targets).Count -ne 2) { throw 'Manifest must describe exactly two game targets.' }
    return $manifest
}

function Get-ManifestTargets {
    param(
        [Parameter(Mandatory=$true)]$Manifest,
        [string]$GameRoot = '',
        [string]$PackageRoot = ''
    )
    $ids = @{}
    $rels = @{}
    $result = @()
    foreach ($target in @($Manifest.game.targets)) {
        $id = [string]$target.id
        $rel = ([string]$target.relative_path).Replace('/', [IO.Path]::DirectorySeparatorChar)
        $payloadRel = ([string]$target.payload_path).Replace('/', [IO.Path]::DirectorySeparatorChar)
        $backupName = [string]$target.backup_name
        if (-not $id -or $id -notmatch '^[a-z0-9_]+$') { throw "Invalid target id: $id" }
        if ($ids.ContainsKey($id)) { throw "Duplicate target id: $id" }
        if ($rels.ContainsKey($rel.ToLowerInvariant())) { throw "Duplicate target path: $rel" }
        if ([string]$target.baseline_sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
            [string]$target.patched_sha256 -notmatch '^[0-9a-fA-F]{64}$') {
            throw "Invalid target hashes: $id"
        }
        if (-not $backupName -or [IO.Path]::GetFileName($backupName) -ne $backupName) {
            throw "Invalid backup name: $backupName"
        }
        $record = [ordered]@{
            Id = $id
            RelativePath = $rel
            PayloadRelativePath = $payloadRel
            BackupName = $backupName
            BaselineSize = [int64]$target.baseline_size
            BaselineHash = ([string]$target.baseline_sha256).ToLowerInvariant()
            PatchedSize = [int64]$target.patched_size
            PatchedHash = ([string]$target.patched_sha256).ToLowerInvariant()
        }
        if ($GameRoot) {
            $game = Get-CanonicalPath $GameRoot
            $full = Get-CanonicalPath (Join-Path $game $rel)
            if (-not (Test-IsSameOrChildPath $full $game)) { throw "Target path escapes game root: $rel" }
            $record.TargetPath = $full
        }
        if ($PackageRoot) {
            $package = Get-CanonicalPath $PackageRoot
            $payload = Get-CanonicalPath (Join-Path $package $payloadRel)
            if (-not (Test-IsSameOrChildPath $payload $package)) { throw "Payload path escapes package root: $payloadRel" }
            $record.PayloadPath = $payload
        }
        $ids[$id] = $true
        $rels[$rel.ToLowerInvariant()] = $true
        $result += [pscustomobject]$record
    }
    return @($result)
}

function Get-TargetsState {
    param([Parameter(Mandatory=$true)][array]$Targets)
    $items = @()
    foreach ($target in $Targets) {
        $state = 'missing'
        $size = $null
        $hash = $null
        if (Test-Path -LiteralPath $target.TargetPath -PathType Leaf) {
            $item = Get-Item -LiteralPath $target.TargetPath -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Target reparse point rejected: $($target.TargetPath)"
            }
            $size = [int64]$item.Length
            $hash = Get-Sha256 $target.TargetPath
            if ($size -eq $target.BaselineSize -and $hash -eq $target.BaselineHash) {
                $state = 'original'
            } elseif ($size -eq $target.PatchedSize -and $hash -eq $target.PatchedHash) {
                $state = 'korean'
            } else {
                $state = 'unsupported'
            }
        }
        $items += [pscustomobject][ordered]@{
            id=$target.Id; path=$target.TargetPath; state=$state; size=$size; sha256=$hash
        }
    }
    $states = @($items | ForEach-Object { $_.state })
    if (@($states | Where-Object { $_ -eq 'original' }).Count -eq $Targets.Count) {
        $overall = 'original'
    } elseif (@($states | Where-Object { $_ -eq 'korean' }).Count -eq $Targets.Count) {
        $overall = 'korean'
    } elseif (@($states | Where-Object { $_ -in @('missing','unsupported') }).Count -gt 0) {
        $overall = 'unsupported'
    } else {
        $overall = 'mixed'
    }
    return [pscustomobject][ordered]@{overall=$overall; targets=$items}
}

function Set-TargetFromSource {
    param(
        [Parameter(Mandatory=$true)]$Target,
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$ExpectedHash,
        [Parameter(Mandatory=$true)][string]$TransactionId,
        [Parameter(Mandatory=$true)][string]$Phase
    )
    if (-not (Test-Path -LiteralPath $Target.TargetPath -PathType Leaf)) {
        throw "Missing target: $($Target.TargetPath)"
    }
    $dir = Split-Path -Parent $Target.TargetPath
    $safeId = ([string]$Target.Id) -replace '[^a-zA-Z0-9_]','_'
    $incoming = Join-Path $dir ('.cgko_{0}_{1}_{2}.tmp' -f $Phase,$TransactionId,$safeId)
    $old = Join-Path $dir ('.cgko_{0}_old_{1}_{2}.tmp' -f $Phase,$TransactionId,$safeId)
    try {
        Copy-AndVerify $Source $incoming $ExpectedHash
        [IO.File]::Replace($incoming, $Target.TargetPath, $old, $true)
        if ((Get-Sha256 $Target.TargetPath) -ne $ExpectedHash.ToLowerInvariant()) {
            throw "Replacement verification failed: $($Target.TargetPath)"
        }
    } finally {
        Remove-Item -LiteralPath $incoming,$old -Force -ErrorAction SilentlyContinue
    }
}

function Remove-TransactionTemps {
    param([Parameter(Mandatory=$true)][array]$Targets, [Parameter(Mandatory=$true)][string]$TransactionId)
    foreach ($dir in @($Targets | ForEach-Object { Split-Path -Parent $_.TargetPath } | Sort-Object -Unique)) {
        Get-ChildItem -LiteralPath $dir -File -Filter ('.cgko_*{0}*' -f $TransactionId) -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
}
