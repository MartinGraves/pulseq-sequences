param(
    [string]$TargetRoot = "F:\Programming\mrzero-ernst-optimisation",
    [string]$EnvironmentPath = "C:\PythonEnvs\mrzero-ernst",
    [switch]$SkipMrzeroRun
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "MRzero Ernst-angle project installer"
Write-Host "Project:     $TargetRoot"
Write-Host "Environment: $EnvironmentPath"
Write-Host ""

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "The Windows Python launcher (py.exe) was not found. Install 64-bit Python 3.12, then run this installer again."
}

$versionText = & py -3.12 --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 is not available through py.exe. Install 64-bit Python 3.12, then run this installer again."
}
Write-Host "Using $versionText"

$projectDirectories = @(
    "F:\Programming",
    $TargetRoot,
    (Join-Path $TargetRoot "results"),
    (Join-Path $TargetRoot "results\mrzero"),
    (Join-Path $TargetRoot "figures"),
    (Join-Path $TargetRoot "data"),
    (Join-Path $TargetRoot "logs"),
    "C:\PythonEnvs"
)

foreach ($directory in $projectDirectories) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$projectCommit = "4a10d5aa69eff002fba3d522fa666d5569b25805"
$baseUrl = "https://raw.githubusercontent.com/MartinGraves/pulseq-sequences/$projectCommit/mrzero-ernst-optimisation"
$projectFiles = @(
    "README.md",
    "requirements.txt",
    "ernst_optimisation.py",
    "mrzero_validation.py",
    "test_ernst_optimisation.py",
    "run_all.ps1"
)

Write-Host "Downloading project files..."
foreach ($fileName in $projectFiles) {
    $source = "$baseUrl/$fileName"
    $destination = Join-Path $TargetRoot $fileName
    Invoke-WebRequest -Uri $source -OutFile $destination
    Write-Host "  $fileName"
}

Set-Location $TargetRoot

$venvPython = Join-Path $EnvironmentPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating Python 3.12 virtual environment at $EnvironmentPath..."
    & py -3.12 -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual-environment creation failed."
    }
}

Write-Host "Upgrading pip..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed."
}

Write-Host "Installing PyTorch, MRzero Core, PyPulseq, and analysis packages..."
& $venvPython -m pip install -r (Join-Path $TargetRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Package installation failed."
}

Write-Host "Recording installed package versions..."
& $venvPython -m pip freeze |
    Set-Content -Path (Join-Path $TargetRoot "logs\installed_packages.txt") -Encoding UTF8

Write-Host "Running scientific regression tests..."
& $venvPython -m unittest -v test_ernst_optimisation.py 2>&1 |
    Tee-Object -FilePath (Join-Path $TargetRoot "logs\tests.log")
if ($LASTEXITCODE -ne 0) {
    throw "Regression tests failed. See logs\tests.log."
}

Write-Host "Running differentiable Ernst-angle and contrast experiments..."
& $venvPython ernst_optimisation.py 2>&1 |
    Tee-Object -FilePath (Join-Path $TargetRoot "logs\ernst_optimisation.log")
if ($LASTEXITCODE -ne 0) {
    throw "Ernst-angle experiment failed. See logs\ernst_optimisation.log."
}

if (-not $SkipMrzeroRun) {
    Write-Host "Running MRzero/Pulseq validation..."
    & $venvPython mrzero_validation.py 2>&1 |
        Tee-Object -FilePath (Join-Path $TargetRoot "logs\mrzero_validation.log")
    if ($LASTEXITCODE -ne 0) {
        throw "MRzero validation failed. See logs\mrzero_validation.log."
    }
}

Write-Host ""
Write-Host "Installation and validation complete."
Write-Host "Project:     $TargetRoot"
Write-Host "Environment: $EnvironmentPath"
Write-Host "Python:      $venvPython"
Write-Host "Results:     $(Join-Path $TargetRoot 'results')"
Write-Host "Logs:        $(Join-Path $TargetRoot 'logs')"
