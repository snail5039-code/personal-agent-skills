[CmdletBinding()]
param(
    [string[]]$Skill = @('til', 'cover-letter-writing')
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$skillRoot = Join-Path $codexRoot 'skills'

New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null

foreach ($name in $Skill) {
    $source = Join-Path $repoRoot $name
    $destination = Join-Path $skillRoot $name

    if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md'))) {
        throw "Skill '$name' was not found in this repository."
    }

    if (Test-Path -LiteralPath $destination) {
        Write-Warning "Skipped '$name': $destination already exists."
        continue
    }

    Copy-Item -LiteralPath $source -Destination $destination -Recurse
    Write-Host "Installed '$name' to $destination"
}

