[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Release = Join-Path $ProjectRoot "outputs\latest\country_risk.csv"

Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath $Release -PathType Leaf)) {
        throw "Frontend data is missing. Run scripts\run_pipeline.ps1 first."
    }
    & uv run --frozen streamlit run app/streamlit_app.py
    if ($LASTEXITCODE -ne 0) {
        throw "Streamlit exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
