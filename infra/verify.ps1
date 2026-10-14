# WattWise AI - Post-deployment verification
# =============================================================================
# Hits the deployed Streamlit + Mock BMS endpoints and verifies they respond.
# Reads the deployment tracking file to find the container group FQDN.
#
# Usage:  ./verify.ps1
# =============================================================================

$SUBSCRIPTION_ID = "23724963-04db-44e4-8858-55c4bcd63dc8"
$RG              = "rg-pSiddhi3.0-2026-01-sem4-Arunn"
$TRACKING_FILE   = Join-Path $PSScriptRoot ".deployed-resources.json"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] >>> $msg" -ForegroundColor Cyan
}
function Write-OK($msg) { Write-Host "       [OK] $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "       [FAIL] $msg" -ForegroundColor Red }

if (-not (Test-Path $TRACKING_FILE)) {
    Write-Fail "No deployment tracked. Run deploy.ps1 first."
    exit 1
}

az account set --subscription $SUBSCRIPTION_ID | Out-Null

$tracking = Get-Content $TRACKING_FILE -Raw | ConvertFrom-Json
$acgResource = $tracking.resources | Where-Object { $_.type -eq "container-group" }
if (-not $acgResource) {
    Write-Fail "No container group tracked"
    exit 1
}
$acgName = $acgResource.name

Write-Step "Fetching Container Group FQDN"
$fqdn = (az container show -g $RG -n $acgName --query "ipAddress.fqdn" -o tsv 2>&1).Trim()
$state = (az container show -g $RG -n $acgName --query "instanceView.state" -o tsv 2>&1).Trim()
Write-OK "FQDN: $fqdn"
Write-OK "State: $state"

$streamUrl = "http://${fqdn}:8501"
$bmsUrl    = "http://${fqdn}:9100"
$results   = @()

Write-Step "Checking Streamlit health endpoint"
try {
    $r = Invoke-WebRequest -Uri "$streamUrl/_stcore/health" -TimeoutSec 30 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        Write-OK "Streamlit health OK (HTTP $($r.StatusCode))"
        $results += [PSCustomObject]@{ Check = "Streamlit /_stcore/health"; Status = "OK" }
    } else {
        Write-Fail "Streamlit returned HTTP $($r.StatusCode)"
        $results += [PSCustomObject]@{ Check = "Streamlit health"; Status = "HTTP $($r.StatusCode)" }
    }
} catch {
    Write-Fail "Streamlit unreachable: $($_.Exception.Message)"
    $results += [PSCustomObject]@{ Check = "Streamlit health"; Status = "UNREACHABLE" }
}

Write-Step "Checking Mock BMS health endpoint"
try {
    $r = Invoke-WebRequest -Uri "$bmsUrl/health" -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        $body = $r.Content
        Write-OK "Mock BMS health OK: $body"
        $results += [PSCustomObject]@{ Check = "Mock BMS /health"; Status = "OK" }
    } else {
        Write-Fail "Mock BMS returned HTTP $($r.StatusCode)"
        $results += [PSCustomObject]@{ Check = "Mock BMS health"; Status = "HTTP $($r.StatusCode)" }
    }
} catch {
    Write-Fail "Mock BMS unreachable: $($_.Exception.Message)"
    $results += [PSCustomObject]@{ Check = "Mock BMS health"; Status = "UNREACHABLE" }
}

Write-Step "Checking Mock BMS state endpoint"
try {
    $r = Invoke-WebRequest -Uri "$bmsUrl/api/state" -TimeoutSec 15 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        $facilities = ($r.Content | ConvertFrom-Json).Count
        Write-OK "Mock BMS state OK ($facilities facilities)"
        $results += [PSCustomObject]@{ Check = "Mock BMS /api/state"; Status = "OK ($facilities facilities)" }
    }
} catch {
    Write-Fail "Mock BMS state unreachable: $($_.Exception.Message)"
    $results += [PSCustomObject]@{ Check = "Mock BMS state"; Status = "UNREACHABLE" }
}

Write-Step "Container logs (last 20 lines each)"
Write-Host ""
Write-Host "--- streamlit container ---" -ForegroundColor Yellow
az container logs -g $RG -n $acgName --container-name streamlit --tail 20 2>&1
Write-Host ""
Write-Host "--- bms container ---" -ForegroundColor Yellow
az container logs -g $RG -n $acgName --container-name bms --tail 20 2>&1

Write-Step "Summary"
$results | Format-Table -AutoSize

Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host "   URLs" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
Write-Host "   Dashboard: $streamUrl" -ForegroundColor Yellow
Write-Host "   Mock BMS : $bmsUrl" -ForegroundColor Yellow
Write-Host ""
