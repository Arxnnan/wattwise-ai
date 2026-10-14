# WattWise AI - Teardown script
# =============================================================================
# Reads .deployed-resources.json (created by deploy.ps1) and deletes EACH
# resource BY EXACT NAME. Never uses wildcards. Will not touch anything that
# wasn't tracked by the matching deploy.
#
# Usage:  ./teardown.ps1
# =============================================================================

$ErrorActionPreference = "Continue"  # keep deleting even if one step fails

$SUBSCRIPTION_ID = "23724963-04db-44e4-8858-55c4bcd63dc8"
$RG              = "rg-pSiddhi3.0-2026-01-sem4-Arunn"
$TRACKING_FILE   = Join-Path $PSScriptRoot ".deployed-resources.json"

function Write-Step($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host ""
    Write-Host "[$ts] >>> $msg" -ForegroundColor Cyan
}
function Write-OK($msg)   { Write-Host "       [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "       [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "       [FAIL] $msg" -ForegroundColor Red }

if (-not (Test-Path $TRACKING_FILE)) {
    Write-Fail "Tracking file not found: $TRACKING_FILE"
    Write-Fail "Either nothing was deployed, or the file was deleted."
    Write-Fail "Use 'az resource list -g $RG' to inspect manually."
    exit 1
}

$tracking = Get-Content $TRACKING_FILE -Raw | ConvertFrom-Json
Write-Host "Deployed at: $($tracking.deployed_at)"
Write-Host "Resources to delete: $($tracking.resources.Count)"
$tracking.resources | ForEach-Object { Write-Host "  - $($_.type): $($_.name)" }
Write-Host ""
$answer = Read-Host "Delete all of the above? Type 'yes' to confirm"
if ($answer -ne "yes") {
    Write-Warn "Aborted. Nothing deleted."
    exit 0
}

az account set --subscription $SUBSCRIPTION_ID | Out-Null

# Delete in REVERSE order to respect dependencies
# (container group -> app insights -> log analytics -> key vault -> acr)
$ordered = $tracking.resources | Sort-Object @{
    Expression = {
        switch ($_.type) {
            "container-group" { 1 }
            "app-insights"    { 2 }
            "log-analytics"   { 3 }
            "key-vault"       { 4 }
            "acr"             { 5 }
            default            { 9 }
        }
    }
}

foreach ($r in $ordered) {
    Write-Step ("Deleting " + $r.type + ": " + $r.name)
    switch ($r.type) {
        "acr" {
            az acr delete -g $RG -n $r.name --yes --only-show-errors 2>&1 | Out-Null
        }
        "key-vault" {
            az keyvault delete -g $RG -n $r.name --only-show-errors 2>&1 | Out-Null
            # Purge so the name becomes immediately re-usable
            $loc = az keyvault show-deleted -n $r.name --query properties.location -o tsv 2>&1
            if ($LASTEXITCODE -eq 0 -and $loc) {
                az keyvault purge -n $r.name --location $loc --only-show-errors 2>&1 | Out-Null
            }
        }
        "log-analytics" {
            az monitor log-analytics workspace delete -g $RG -n $r.name --yes --force true --only-show-errors 2>&1 | Out-Null
        }
        "app-insights" {
            az monitor app-insights component delete -g $RG -a $r.name --only-show-errors 2>&1 | Out-Null
        }
        "container-group" {
            az container delete -g $RG -n $r.name --yes --only-show-errors 2>&1 | Out-Null
        }
        default {
            Write-Warn "Unknown resource type: $($r.type). Skipping."
            continue
        }
    }
    if ($LASTEXITCODE -eq 0) {
        Write-OK "deleted"
    } else {
        Write-Warn "may already be gone or had an error"
    }
}

# Final verification pass
Write-Step "Final RG state"
az resource list -g $RG --query "[].{name:name, type:type}" -o table 2>&1

# Delete tracking file (deploy is now done)
Remove-Item $TRACKING_FILE -ErrorAction SilentlyContinue
Write-OK "Tracking file removed"

Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host "   TEARDOWN COMPLETE" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
