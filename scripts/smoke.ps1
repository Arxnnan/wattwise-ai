# WattWise AI - smoke-test a running deployment (local or Azure).
# Hits key endpoints, verifies they respond, and reports per-endpoint pass/fail.
#
# Usage:
#   ./scripts/smoke.ps1                                      # local defaults
#   ./scripts/smoke.ps1 -Host "ww152650-wattwise.eastus.azurecontainer.io"
#
# Exit code 0 = all green, 1 = any failure.

[CmdletBinding()]
param(
    [string]$HostName = "localhost",
    [int]$StreamlitPort = 8501,
    [int]$BmsPort = 9100,
    [int]$TimeoutSec = 15
)

$ErrorActionPreference = "Continue"
$streamlit = "http://${HostName}:${StreamlitPort}"
$bms       = "http://${HostName}:${BmsPort}"
$results = @()

function Check($name, $url, [scriptblock]$extraCheck) {
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec $TimeoutSec -UseBasicParsing
        if ($r.StatusCode -ne 200) {
            $script:results += [PSCustomObject]@{ Check=$name; Status="FAIL"; Detail="HTTP $($r.StatusCode)" }
            return
        }
        if ($extraCheck) {
            $errMsg = & $extraCheck $r
            if ($errMsg) {
                $script:results += [PSCustomObject]@{ Check=$name; Status="FAIL"; Detail=$errMsg }
                return
            }
        }
        $script:results += [PSCustomObject]@{ Check=$name; Status="PASS"; Detail="HTTP $($r.StatusCode)" }
    } catch {
        $script:results += [PSCustomObject]@{ Check=$name; Status="FAIL"; Detail=$_.Exception.Message.Substring(0, [Math]::Min(80, $_.Exception.Message.Length)) }
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   WattWise AI - smoke test  (host: $HostName)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Check "Streamlit health" "$streamlit/_stcore/health"
Check "Streamlit root HTML served" "$streamlit/" {
    param($r)
    if ($r.Content -notmatch "Streamlit|WattWise") { "page did not contain Streamlit markers" }
}
Check "Mock BMS /health" "$bms/health" {
    param($r)
    if ($r.Content -notmatch "ok") { "did not return ok status" }
}
Check "Mock BMS /api/state (3 facilities expected)" "$bms/api/state" {
    param($r)
    try {
        $data = $r.Content | ConvertFrom-Json
        if ($data.Count -lt 3) { "expected 3 facilities, got $($data.Count)" }
    } catch { "JSON parse failed" }
}
Check "Mock BMS console HTML served" "$bms/" {
    param($r)
    if ($r.Content -notmatch "Mock BMS") { "page did not contain Mock BMS marker" }
}

# -------- POST a command through Mock BMS to prove the write path --------
Write-Host "`nTesting POST /command..." -ForegroundColor Yellow
try {
    $body = @{
        facility = "office"
        action_type = "shed_load"
        loads = @("HVAC-A")
        shed_kw = 10
    } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$bms/command" -Method POST -Body $body -ContentType "application/json" -TimeoutSec $TimeoutSec -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        $results += [PSCustomObject]@{ Check="Mock BMS POST /command"; Status="PASS"; Detail="shed accepted" }
    } else {
        $results += [PSCustomObject]@{ Check="Mock BMS POST /command"; Status="FAIL"; Detail="HTTP $($r.StatusCode)" }
    }
} catch {
    $results += [PSCustomObject]@{ Check="Mock BMS POST /command"; Status="FAIL"; Detail=$_.Exception.Message.Substring(0, 80) }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   RESULTS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$fails = @($results | Where-Object { $_.Status -eq "FAIL" }).Count
if ($fails -eq 0) {
    Write-Host "ALL ENDPOINTS GREEN" -ForegroundColor Green
    exit 0
} else {
    Write-Host "$fails endpoint(s) failed" -ForegroundColor Red
    exit 1
}
