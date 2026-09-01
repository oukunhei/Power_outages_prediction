[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

Push-Location $ProjectRoot
try {
    & uv run --frozen outage-prediction build-legacy --config config/project.yaml
    if ($LASTEXITCODE -ne 0) {
        throw "Risk-data build failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
