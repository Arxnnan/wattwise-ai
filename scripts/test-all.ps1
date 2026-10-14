# WattWise AI - run every automated test in sequence, print one green/red summary.
# Usage:
#   ./scripts/test-all.ps1              # full suite (unit + integration + model-accuracy + lint)
#   ./scripts/test-all.ps1 -Fast        # skip model-accuracy (saves ~30s on Chronos load)
#   ./scripts/test-all.ps1 -NoLint      # skip ruff
# Exit code 0 = all green, 1 = any failure.

[CmdletBinding()]
param(
    [switch]$Fast,
    [switch]$NoLint
)

$ErrorActionPreference = "Continue"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Virtualenv not found at .venv" -ForegroundColor Red; exit 1 }

$results = @()
function Record($name, $exitCode, $detail) {
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $script:results += [PSCustomObject]@{ Suite=$name; Status=$status; Detail=$detail }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   WattWise AI - test-all" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# -------- Lint --------
if (-not $NoLint) {
    Write-Host "`n[1/4] Lint (ruff)..." -ForegroundColor Yellow
    & $py -m ruff check . --quiet 2>&1 | Select-Object -Last 10
    Record "Lint (ruff)" $LASTEXITCODE "ruff check ."
}

# -------- Unit tests --------
Write-Host "`n[2/4] Unit tests..." -ForegroundColor Yellow
& $py -m pytest tests/unit/ -q --tb=line --no-header 2>&1 | Select-Object -Last 5
Record "Unit tests" $LASTEXITCODE "pytest tests/unit/"

# -------- Integration tests --------
Write-Host "`n[3/4] Integration tests..." -ForegroundColor Yellow
& $py -m pytest tests/integration/ -q --tb=line --no-header 2>&1 | Select-Object -Last 5
Record "Integration tests" $LASTEXITCODE "pytest tests/integration/"

# -------- Model accuracy gates --------
if (-not $Fast) {
    Write-Host "`n[4/4] Model accuracy gates (Chronos loads, ~30s)..." -ForegroundColor Yellow
    & $py -m pytest tests/model_accuracy/ -q --tb=line --no-header 2>&1 | Select-Object -Last 5
    Record "Model accuracy" $LASTEXITCODE "pytest tests/model_accuracy/"
} else {
    Record "Model accuracy" 0 "SKIPPED (-Fast flag)"
}

# -------- Report --------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   RESULTS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$fails = @($results | Where-Object { $_.Status -eq "FAIL" }).Count
if ($fails -eq 0) {
    Write-Host "ALL GREEN" -ForegroundColor Green
    exit 0
} else {
    Write-Host "$fails suite(s) failed" -ForegroundColor Red
    exit 1
}
