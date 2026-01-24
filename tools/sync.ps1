param(
    [ValidateSet("pull", "publish", "status")]
    [string]$Mode = "status"
)

function Die($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

# Ensure we're in the repo root even if launched from elsewhere
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Basic checks
git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { Die "Not inside a git repository: $repo" }

Write-Host ""
Write-Host "Repo: $repo" -ForegroundColor Cyan
Write-Host ""

if ($Mode -eq "status") {
    git status
    exit 0
}

if ($Mode -eq "pull") {
    Write-Host "Step 1/2: Fetching..." -ForegroundColor Yellow
    git fetch --prune
    if ($LASTEXITCODE -ne 0) { Die "git fetch failed" }

    Write-Host "Step 2/2: Pulling..." -ForegroundColor Yellow
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Pull failed (likely because you have local changes)." -ForegroundColor Red
        Write-Host "Tip: run 'git status' and commit/stash changes before pulling." -ForegroundColor DarkYellow
        exit 2
    }

    Write-Host ""
    Write-Host "✅ Up to date." -ForegroundColor Green
    git status
    exit 0
}

if ($Mode -eq "publish") {
    Write-Host "Reminder: Did you pull first?" -ForegroundColor DarkYellow
    Write-Host "Run: tools\sync.ps1 pull" -ForegroundColor DarkYellow
    Write-Host ""

    # Show changes
    git status

    # Nothing to do?
    $porcelain = git status --porcelain
    if ([string]::IsNullOrWhiteSpace($porcelain)) {
        Write-Host ""
        Write-Host "Nothing to publish." -ForegroundColor Green
        exit 0
    }

    Write-Host ""
    Write-Host "Staging: matlab/ seq/ docs/ INSTALLATION.md README.md" -ForegroundColor Yellow

    # Stage common paths (adjust as you like)
    git add matlab seq docs INSTALLATION.md README.md 2>$null
    git add .vscode 2>$null

    # Re-check staging
    $staged = git diff --cached --name-only
    if ([string]::IsNullOrWhiteSpace($staged)) {
        Write-Host ""
        Write-Host "Nothing staged. (Maybe your changes are elsewhere?)" -ForegroundColor Red
        Write-Host "Tip: run 'git status' and stage the files you want." -ForegroundColor DarkYellow
        exit 3
    }

    Write-Host ""
    Write-Host "Staged files:" -ForegroundColor Cyan
    $staged

    Write-Host ""
    Write-Host "Write a useful commit message:" -ForegroundColor Yellow
    Write-Host "Examples:" -ForegroundColor DarkGray
    Write-Host "  Add GRE demo with RF spoiling"
    Write-Host "  Fix timing check in demo_gre_cartesian"
    Write-Host "  Document install steps for new PC"
    Write-Host ""

    $msg = Read-Host "Commit message"
    if ([string]::IsNullOrWhiteSpace($msg)) { Die "Commit message cannot be empty" }

    # Helpful prompt for “what & why”
    Write-Host ""
    $body = Read-Host "Optional notes (what changed / why). Press Enter to skip"

    if ([string]::IsNullOrWhiteSpace($body)) {
        git commit -m "$msg"
    }
    else {
        git commit -m "$msg" -m "$body"
    }
    if ($LASTEXITCODE -ne 0) { Die "git commit failed" }

    Write-Host ""
    Write-Host "Pushing..." -ForegroundColor Yellow
    git push
    if ($LASTEXITCODE -ne 0) { Die "git push failed" }

    Write-Host ""
    Write-Host "✅ Published to GitHub." -ForegroundColor Green
    exit 0
}
