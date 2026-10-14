# WattWise AI - run the Locust MQTT load test against a running Mosquitto broker.
# Scope (same as docstring in tests/load/locustfile.py): measures MQTT publish-call
# latency under concurrent meter load. Does NOT measure end-to-end DB write.
#
# Usage:
#   ./scripts/load-test.ps1              # quick: 100 meters, 2 min, headless
#   ./scripts/load-test.ps1 -Full        # RFP spec: 1000 meters, 1 hour, headless
#   ./scripts/load-test.ps1 -UI          # open the Locust web UI (http://localhost:8089)
#
# Reads results from tests/load/results_stats.csv - the 95%ile column
# must be < 2000 ms per RFP target.

[CmdletBinding()]
param(
    [switch]$Full,
    [switch]$UI,
    [string]$MqttHost = "localhost",
    [int]$MqttPort = 1883
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Virtualenv not found at .venv" -ForegroundColor Red; exit 1 }

# Verify Mosquitto is reachable first
Write-Host "Checking MQTT broker at ${MqttHost}:${MqttPort}..." -ForegroundColor Yellow
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect($MqttHost, $MqttPort, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(3000, $false)
    if (-not $ok) { throw "connect timed out" }
    $tcp.EndConnect($iar) | Out-Null
    $tcp.Close()
    Write-Host "  [OK] broker reachable" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] broker not reachable - start Mosquitto first (podman compose up -d mqtt)" -ForegroundColor Red
    exit 1
}

$env:MQTT_HOST = $MqttHost
$env:MQTT_PORT = "$MqttPort"

if ($UI) {
    Write-Host "`nStarting Locust web UI at http://localhost:8089 ..." -ForegroundColor Cyan
    & $py -m locust -f tests/load/locustfile.py --host "tcp://${MqttHost}:${MqttPort}"
    exit $LASTEXITCODE
}

if ($Full) {
    $users = 1000
    $spawn = 100
    $runtime = "1h"
    Write-Host "`nRunning FULL load test: 1000 meters, 1 hour, headless" -ForegroundColor Cyan
} else {
    $users = 100
    $spawn = 25
    $runtime = "2m"
    Write-Host "`nRunning QUICK load test: 100 meters, 2 min, headless" -ForegroundColor Cyan
}

$csvPrefix = "tests/load/results"
& $py -m locust -f tests/load/locustfile.py `
    --host "tcp://${MqttHost}:${MqttPort}" `
    -u $users -r $spawn --run-time $runtime --headless `
    --csv=$csvPrefix

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nLocust reported non-zero exit code" -ForegroundColor Red
    exit $LASTEXITCODE
}

# Parse results
$statsFile = "${csvPrefix}_stats.csv"
if (Test-Path $statsFile) {
    Write-Host "`n============================================================" -ForegroundColor Cyan
    Write-Host "   RESULTS  (${statsFile})" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    $rows = Import-Csv $statsFile
    $rows | Where-Object { $_.Name -ne "Aggregated" } | Select-Object Name, "Request Count", "Failure Count", "Average Response Time", "95%" | Format-Table -AutoSize

    $aggregated = $rows | Where-Object { $_.Name -eq "Aggregated" } | Select-Object -First 1
    if ($aggregated) {
        $p95 = [double]$aggregated."95%"
        $target = 2000
        Write-Host "Aggregated p95: ${p95} ms   (RFP target: < ${target} ms)"
        if ($p95 -lt $target) {
            Write-Host "p95 LATENCY GATE: PASS" -ForegroundColor Green
            exit 0
        } else {
            Write-Host "p95 LATENCY GATE: FAIL" -ForegroundColor Red
            exit 1
        }
    }
}
