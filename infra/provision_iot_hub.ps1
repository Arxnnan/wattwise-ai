# WattWise AI — Azure IoT Hub provisioning + UC-01 evidence capture
#
# Closes RFP UC-01 ("IoT Hub consumption data ingestion operational").
# Creates the F1 (FREE) hub, registers the simulator's devices, and writes a
# timestamped evidence file for the review.
#
# Run:
#   az login
#   .\infra\provision_iot_hub.ps1
#
# Cost: Rs.0. IoT Hub F1 is free permanently (1 per subscription,
# 8,000 messages/day) - it is NOT a 12-month trial benefit.
#
# If this fails with AuthorizationFailed, that is ALSO a useful result: it is
# dated proof of the Contributor-role blocker noted in provision_azure.ps1.
# The evidence file records either outcome.

$ErrorActionPreference = "Continue"

$RG           = "rg-pSiddhi3.0-2026-01-sem4-Arunn"
$SUBSCRIPTION = "23724963-04db-44e4-8858-55c4bcd63dc8"
$LOC          = "eastus"
# Hub names are globally unique; suffix keeps re-runs from colliding.
$HUB          = "wattwise-hub-$(Get-Random -Minimum 1000 -Maximum 9999)"
$EVIDENCE     = "docs\midterm\UC01_IOT_HUB_EVIDENCE.md"

# Device IDs must match ingestion/simulator.py FACILITIES
$DEVICES = @(
    "off-main-01","off-sub-hvac","off-hvac-01","off-light-01","off-occ-01","off-wx-01",
    "wh-main-01","wh-sub-light","wh-hvac-01","wh-light-01","wh-occ-01","wh-wx-01",
    "dc-main-01","dc-sub-cooling","dc-hvac-01","dc-light-01","dc-occ-01","dc-wx-01"
)

$stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss 'UTC'zzz")
$log = New-Object System.Collections.ArrayList
function Note($s) { [void]$log.Add($s); Write-Host $s }

Note "=== WattWise AI - IoT Hub provisioning ==="
Note "Attempted at: $stamp"
Note "Resource group: $RG"
Note ""

az account set --subscription $SUBSCRIPTION 2>&1 | Out-Null
$acct = az account show --output json 2>&1 | ConvertFrom-Json
if (-not $acct) { Note "ERROR: not logged in. Run 'az login' first."; exit 1 }
Note "Signed in as : $($acct.user.name)"
Note "Subscription : $($acct.name) ($($acct.id))"
Note ""

# --- 1. Create the free F1 hub -------------------------------------------
Note "[1/4] Creating IoT Hub '$HUB' (SKU F1, FREE)..."
$createOut = az iot hub create `
    --name $HUB `
    --resource-group $RG `
    --sku F1 `
    --partition-count 2 `
    --location $LOC `
    --output json 2>&1

if ($LASTEXITCODE -ne 0) {
    Note ""
    Note "RESULT: FAILED"
    Note "Azure returned:"
    Note ($createOut | Out-String)
    Note ""
    if ("$createOut" -match "AuthorizationFailed|does not have authorization|Forbidden") {
        Note "DIAGNOSIS: Permission blocker CONFIRMED."
        Note "The signed-in principal cannot create IoT Hub in this resource group."
        Note "This matches the note in provision_azure.ps1:"
        Note "  'IoT Hub to be created by L&D (requires Contributor role).'"
        Note "ACTION: attach this file to the UC-01 appeal as dated proof, and"
        Note "        request L&D provision the hub or grant Contributor."
    } elseif ("$createOut" -match "quota|already.*free|F1.*exceed") {
        Note "DIAGNOSIS: a free F1 hub already exists on this subscription"
        Note "           (limit is 1). Reuse it - list with: az iot hub list -o table"
    }
    $log | Set-Content -Path $EVIDENCE -Encoding utf8
    Note "Evidence written to $EVIDENCE"
    exit 1
}

Note "IoT Hub created."
Note ""

# --- 2. Register the simulator's devices ----------------------------------
Note "[2/4] Registering $($DEVICES.Count) devices..."
foreach ($d in $DEVICES) {
    az iot hub device-identity create --hub-name $HUB --device-id $d --output none 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Note "  registered: $d" } else { Note "  FAILED: $d" }
}
Note ""

# --- 3. Capture connection strings ---------------------------------------
Note "[3/4] Retrieving connection strings..."
$hubCs = az iot hub connection-string show --hub-name $HUB --output tsv 2>&1
$devCs = az iot hub device-identity connection-string show `
            --hub-name $HUB --device-id "off-main-01" --output tsv 2>&1
Note "  service CS retrieved: $([bool]$hubCs)"
Note "  device  CS retrieved: $([bool]$devCs)"
Note "  (values intentionally NOT written to the evidence file)"
Note ""

# --- 4. Verify + record ---------------------------------------------------
Note "[4/4] Verifying..."
$hub = az iot hub show --name $HUB --output json 2>&1 | ConvertFrom-Json
$devCount = (az iot hub device-identity list --hub-name $HUB --output json 2>&1 | ConvertFrom-Json).Count

Note ""
Note "RESULT: SUCCESS"
Note "  Hub name      : $($hub.name)"
Note "  Hostname      : $($hub.properties.hostName)"
Note "  SKU           : $($hub.sku.name) (capacity $($hub.sku.capacity))  <- FREE tier"
Note "  Location      : $($hub.location)"
Note "  State         : $($hub.properties.state)"
Note "  Devices       : $devCount registered"
Note "  Provisioned at: $stamp"
Note ""
Note "Cost: Rs.0 - F1 is the permanent free SKU (8,000 msgs/day)."
Note ""
Note "NEXT: append these to .env (values printed below, not stored in evidence):"
Write-Host ""
Write-Host "IOT_HUB_CONNECTION_STRING=$hubCs"
Write-Host "IOT_HUB_DEVICE_CONNECTION_STRING=$devCs"

$header = @(
    "# UC-01 Evidence - Azure IoT Hub Provisioning",
    "",
    "Generated by ``infra/provision_iot_hub.ps1``. Raw CLI transcript below.",
    "Connection strings are deliberately excluded.",
    "",
    '```'
)
($header + $log + @('```')) | Set-Content -Path $EVIDENCE -Encoding utf8
Note "Evidence written to $EVIDENCE"
