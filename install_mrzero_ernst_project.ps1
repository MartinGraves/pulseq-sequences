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

$pyList = (& py -0p 2>$null | Out-String)
$pythonSelector = $null
foreach ($version in @("3.14", "3.13", "3.12")) {
    if ($pyList -match [regex]::Escape($version)) {
        $pythonSelector = "-$version"
        break
    }
}

if (-not $pythonSelector) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "No compatible Python runtime was found and Windows Package Manager is unavailable. Install 64-bit Python 3.13 from python.org, then rerun this installer."
    }

    Write-Host "No compatible Python runtime was found. Installing Python 3.13..."
    & winget install --exact --id Python.Python.3.13 --scope user --accept-source-agreements --accept-package-agreements
    $pyList = (& py -0p 2>$null | Out-String)
    if ($pyList -match [regex]::Escape("3.13")) {
        $pythonSelector = "-3.13"
    } else {
        throw "Python was installed but is not yet visible to py.exe. Close PowerShell, open it again, and rerun this installer."
    }
}

$versionText = & py $pythonSelector --version 2>$null
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

$projectCommit = "25e88391dfaee1d00536bac486112117db9a6981"
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
    Write-Host "Creating Python virtual environment at $EnvironmentPath..."
    & py $pythonSelector -m venv $EnvironmentPath
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

function Invoke-PythonLogged {
    param(
        [string[]]$PythonArguments,
        [string]$LogPath,
        [string]$FailureMessage
    )

    $stdoutPath = "$LogPath.stdout.tmp"
    $stderrPath = "$LogPath.stderr.tmp"
    Remove-Item $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

    $process = Start-Process -FilePath $venvPython `
        -ArgumentList $PythonArguments `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    $combinedOutput = @()
    if (Test-Path $stdoutPath) {
        $combinedOutput += Get-Content $stdoutPath
    }
    if (Test-Path $stderrPath) {
        $combinedOutput += Get-Content $stderrPath
    }
    $combinedOutput | Tee-Object -FilePath $LogPath
    Remove-Item $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

    if ($process.ExitCode -ne 0) {
        throw "$FailureMessage See $LogPath."
    }
}

Write-Host "Running scientific regression tests..."
Invoke-PythonLogged `
    -PythonArguments @("-m", "unittest", "discover", "-v") `
    -LogPath (Join-Path $TargetRoot "logs\tests.log") `
    -FailureMessage "Regression tests failed."

Write-Host "Running differentiable Ernst-angle and contrast experiments..."
Invoke-PythonLogged `
    -PythonArguments @("ernst_optimisation.py") `
    -LogPath (Join-Path $TargetRoot "logs\ernst_optimisation.log") `
    -FailureMessage "Ernst-angle experiment failed."

if (-not $SkipMrzeroRun) {
    Write-Host "Running MRzero/Pulseq validation..."
    Invoke-PythonLogged `
        -PythonArguments @("mrzero_validation.py") `
        -LogPath (Join-Path $TargetRoot "logs\mrzero_validation.log") `
        -FailureMessage "MRzero validation failed."
}

Write-Host "Optimising minimal brain T1 flip-angle protocols..."
Invoke-PythonLogged `
    -PythonArguments @("optimal_t1_flip_angles.py") `
    -LogPath (Join-Path $TargetRoot "logs\optimal_t1_flip_angles.log") `
    -FailureMessage "T1 flip-angle optimisation failed."

Write-Host ""
Write-Host "Installation and validation complete."
Write-Host "Project:     $TargetRoot"
Write-Host "Environment: $EnvironmentPath"
Write-Host "Python:      $venvPython"
Write-Host "Results:     $(Join-Path $TargetRoot 'results')"
Write-Host "Logs:        $(Join-Path $TargetRoot 'logs')"
