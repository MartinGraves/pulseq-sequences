param(
    [switch]$SkipMrzero,
    [string]$EnvironmentPath = "C:\PythonEnvs\mrzero-ernst"
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "The Windows Python launcher (py.exe) was not found."
}

$python = Join-Path $EnvironmentPath "Scripts\python.exe"
if (-not (Test-Path $python)) {
    $pyList = (& py -0p 2>$null | Out-String)
    $pythonSelector = $null
    foreach ($version in @("3.14", "3.13", "3.12")) {
        if ($pyList -match [regex]::Escape($version)) {
            $pythonSelector = "-$version"
            break
        }
    }
    if (-not $pythonSelector) {
        throw "No compatible Python runtime was found. Python 3.12, 3.13, or 3.14 is required."
    }

    New-Item -ItemType Directory -Path (Split-Path $EnvironmentPath) -Force | Out-Null
    & py $pythonSelector -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the virtual environment at $EnvironmentPath."
    }
}

Set-Location $projectRoot
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $projectRoot "requirements.txt")
& $python -m unittest -v test_ernst_optimisation.py
& $python ernst_optimisation.py

if (-not $SkipMrzero) {
    & $python mrzero_validation.py
}

Write-Host ""
Write-Host "Complete."
Write-Host "Project:     $projectRoot"
Write-Host "Environment: $EnvironmentPath"
Write-Host "Results:     $(Join-Path $projectRoot 'results')"
