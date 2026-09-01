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
    # On some Windows installations, uv's executable trampoline cannot
    # canonicalize console-script paths. Running the module through Python
    # bypasses that wrapper while using the same locked virtual environment.
    & uv run --frozen python -m streamlit run app/streamlit_app.py `
        --server.headless true `
        --browser.gatherUsageStats false
    if ($LASTEXITCODE -ne 0) {
        throw "Streamlit exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
