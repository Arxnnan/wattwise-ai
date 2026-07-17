# WattWise AI — Azure provisioning script
# Resource Group: rg-pSiddhi3.0-2026-01-sem4-Arunn (pre-created by L&D)
# Run: .\infra\provision_azure.ps1
# Requires: az login (already done with pSiddhi subscription)

$RG = "rg-pSiddhi3.0-2026-01-sem4-Arunn"
$LOC = "eastus"
$PREFIX = "wattwise"
$SUBSCRIPTION = "23724963-04db-44e4-8858-55c4bcd63dc8"

Write-Host "=== WattWise AI Azure Provisioning ===" -ForegroundColor Cyan
Write-Host "Resource Group: $RG" -ForegroundColor Yellow
Write-Host "Location: $LOC" -ForegroundColor Yellow

az account set --subscription $SUBSCRIPTION

# 1. Storage Account (Blob for telemetry archive + ML artefacts)
Write-Host "`n[1/4] Creating Storage Account..." -ForegroundColor Cyan
az storage account create `
  --name "${PREFIX}blob2026" `
  --resource-group $RG `
  --location $LOC `
  --sku Standard_LRS `
  --kind StorageV2 `
  --access-tier Hot

az storage container create `
  --account-name "${PREFIX}blob2026" `
  --name "telemetry-archive"

az storage container create `
  --account-name "${PREFIX}blob2026" `
  --name "ml-artefacts"

Write-Host "[1/4] Storage Account done." -ForegroundColor Green

# 2. Azure B1s VM (hosts ClickHouse + Grafana + FastAPI inference)
Write-Host "`n[2/4] Creating B1s VM..." -ForegroundColor Cyan
az vm create `
  --resource-group $RG `
  --name "${PREFIX}-vm" `
  --image Ubuntu2204 `
  --size Standard_B1s `
  --admin-username wattwiseadmin `
  --generate-ssh-keys `
  --public-ip-sku Basic

# Open ports
az vm open-port --resource-group $RG --name "${PREFIX}-vm" --port 8123 --priority 100  # ClickHouse
az vm open-port --resource-group $RG --name "${PREFIX}-vm" --port 3001 --priority 101  # Grafana
az vm open-port --resource-group $RG --name "${PREFIX}-vm" --port 8000 --priority 102  # FastAPI
az vm open-port --resource-group $RG --name "${PREFIX}-vm" --port 8501 --priority 103  # Streamlit

Write-Host "[2/4] VM done." -ForegroundColor Green

# 3. Azure Functions App
Write-Host "`n[3/4] Creating Azure Functions App..." -ForegroundColor Cyan
az functionapp create `
  --resource-group $RG `
  --consumption-plan-location $LOC `
  --runtime python `
  --runtime-version 3.11 `
  --functions-version 4 `
  --name "${PREFIX}-functions" `
  --storage-account "${PREFIX}blob2026" `
  --os-type Linux

Write-Host "[3/4] Functions App done." -ForegroundColor Green

# 4. Budget alert at Rs.1,200 (guardrail)
Write-Host "`n[4/4] Setting budget alert at Rs.1200..." -ForegroundColor Cyan
Write-Host "[4/4] Budget alert configured by L&D (already active)." -ForegroundColor Yellow

Write-Host "`n=== Provisioning complete ===" -ForegroundColor Green
Write-Host "Note: IoT Hub to be created by L&D (requires Contributor role)."
Write-Host "Next: SSH into VM and run docker compose up -d"
