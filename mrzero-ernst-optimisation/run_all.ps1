param(
    [switch]$SkipMrzero
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
}

$python = Resolve-Path ".venv\Scripts\python.exe"

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
& $python -m unittest -v test_ernst_optimisation.py
& $python ernst_optimisation.py

if (-not $SkipMrzero) {
    & $python mrzero_validation.py
}

Write-Host ""
Write-Host "Complete. Results are in the results directory."
