[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$LockFile = Join-Path $ProjectRoot "uv.lock"

Push-Location $ProjectRoot
try {
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -eq $UvCommand) {
        throw @"
uv is not installed or is not available on PATH.
Install it from https://docs.astral.sh/uv/ and run this script again.
"@
    }

    if (-not (Test-Path -LiteralPath $LockFile -PathType Leaf)) {
        throw "uv.lock is missing. Run 'uv lock' once from the project root, then retry."
    }

    Write-Host "Project root: $ProjectRoot"
    Write-Host "uv: $(& uv --version)"
    Write-Host "Creating or synchronizing .venv from the locked dependency set..."

    # The uv cache and this workspace can be on different Windows drives.
    # Copy mode avoids harmless hard-link warnings and behaves consistently.
    & uv sync --locked --all-groups --link-mode copy
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE."
    }

    Write-Host "Running environment verification..."
    & uv run --frozen python scripts/check_env.py
    if ($LASTEXITCODE -ne 0) {
        throw "Environment verification failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "Environment is ready."
    Write-Host "Run commands without activation: uv run <command>"
    Write-Host "Optional activation: .\.venv\Scripts\Activate.ps1"
}
finally {
    Pop-Location
}
