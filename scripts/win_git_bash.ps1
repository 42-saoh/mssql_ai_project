param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

$ErrorActionPreference = "Stop"

if (-not $CommandArgs -or $CommandArgs.Count -eq 0) {
    Write-Error "Usage: powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 <command> [args...]"
}

function Find-FirstExistingPath {
    param([string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Find-WinGetPackagePath {
    param(
        [string]$PackagePattern,
        [string]$ExecutableRelativePath
    )

    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (-not (Test-Path -LiteralPath $packageRoot)) {
        return $null
    }

    $packages = Get-ChildItem -LiteralPath $packageRoot -Directory -Filter $PackagePattern -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending

    foreach ($package in $packages) {
        $candidate = Join-Path $package.FullName $ExecutableRelativePath
        if (Test-Path -LiteralPath $candidate) {
            return (Split-Path -Parent (Resolve-Path -LiteralPath $candidate).Path)
        }
    }

    return $null
}

function Find-CommandDirectory {
    param([string]$CommandName)

    $command = Get-Command $CommandName -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source)) {
        return (Split-Path -Parent (Resolve-Path -LiteralPath $command.Source).Path)
    }

    return $null
}

function Convert-ToBashPath {
    param([string]$Path)

    if (-not $Path) {
        return $null
    }

    $normalized = $Path -replace "\\", "/"
    if ($normalized -match "^([A-Za-z]):/(.*)$") {
        return "/$($Matches[1].ToLowerInvariant())/$($Matches[2])"
    }

    return $normalized
}

function Quote-BashArg {
    param([string]$Value)

    return "'" + ($Value -replace "'", "'\''") + "'"
}

function Test-EnvAssignmentArg {
    param([string]$Value)

    return $Value -match "^[A-Za-z_][A-Za-z0-9_]*=.*$"
}

$gitBash = Find-FirstExistingPath @(
    $env:GIT_BASH,
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe"
)

if (-not $gitBash) {
    Write-Error "Git Bash not found. Install Git for Windows or set GIT_BASH to bash.exe."
}

$pathEntries = New-Object System.Collections.Generic.List[string]

$makePath = Find-WinGetPackagePath "ezwinports.make_*" "bin\make.exe"
if ($makePath) {
    $pathEntries.Add((Convert-ToBashPath $makePath))
}

$pnpmPath = Find-WinGetPackagePath "pnpm.pnpm_*" "pnpm.exe"
if ($pnpmPath) {
    $pathEntries.Add((Convert-ToBashPath $pnpmPath))
}

$nodePath = Find-WinGetPackagePath "OpenJS.NodeJS*" "node.exe"
if (-not $nodePath) {
    $nodePath = Find-CommandDirectory "node.exe"
}
if ($nodePath) {
    $pathEntries.Add((Convert-ToBashPath $nodePath))
}

$pathPrefix = ($pathEntries | Where-Object { $_ }) -join ":"
$leadingEnvAssignments = New-Object System.Collections.Generic.List[string]
$remainingArgs = New-Object System.Collections.Generic.List[string]
$seenCommandArg = $false

foreach ($arg in $CommandArgs) {
    if (-not $seenCommandArg -and (Test-EnvAssignmentArg $arg)) {
        $leadingEnvAssignments.Add($arg)
        continue
    }

    $seenCommandArg = $true
    $remainingArgs.Add($arg)
}

if ($leadingEnvAssignments.Count -gt 0 -and $remainingArgs.Count -eq 0) {
    Write-Error "Environment assignments require a command to run."
}

if ($leadingEnvAssignments.Count -gt 0) {
    $allArgs = @($leadingEnvAssignments.ToArray()) + @($remainingArgs.ToArray())
    $quotedArgs = "env " + (($allArgs | ForEach-Object { Quote-BashArg $_ }) -join " ")
} else {
    $quotedArgs = ($CommandArgs | ForEach-Object { Quote-BashArg $_ }) -join " "
}

if ($pathPrefix) {
    $bashCommand = "export PATH=$(Quote-BashArg $pathPrefix):`$PATH; $quotedArgs"
} else {
    $bashCommand = $quotedArgs
}

& $gitBash -lc $bashCommand
exit $LASTEXITCODE
