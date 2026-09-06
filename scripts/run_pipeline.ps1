[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

Push-Location $ProjectRoot
try {
    # Use Python's module entry point to avoid uv console-script trampoline
    # path failures on Windows.
    & uv run --frozen python -m outage_prediction build --config config/project.yaml
    if ($LASTEXITCODE -ne 0) {
        throw "Risk-data build failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
