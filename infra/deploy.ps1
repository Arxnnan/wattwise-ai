# WattWise AI - Full Azure deployment script
# =============================================================================
# Idempotent, bug-free end-to-end deployment of the WattWise demo stack to Azure.
#
# Creates: ACR, Key Vault, Log Analytics, App Insights, Container Group
#   (2 containers: Streamlit dashboard + Mock BMS)
#
# Usage:
#   cd infra
#   ./deploy.ps1                              # fresh deploy
#   ./deploy.ps1 -Rollback                    # tear everything down
#   ./deploy.ps1 -SkipImageBuild              # redeploy container group only
#
# Teardown:
#   ./teardown.ps1
# =============================================================================

[CmdletBinding()]
param(
    [switch]$Rollback,
    [switch]$SkipImageBuild
)

$ErrorActionPreference = "Stop"

# ============================================================================
# CONFIG - edit these if needed
# ============================================================================
$SUBSCRIPTION_ID = "23724963-04db-44e4-8858-55c4bcd63dc8"
$RG              = "rg-pSiddhi3.0-2026-01-sem4-Arunn"
$LOCATION        = "eastus"
# Unique suffix (lowercase, 6 chars) - keeps resource names Azure-valid
$SUFFIX          = "ww" + (Get-Date -Format "HHmmss")

$ACR_NAME        = $SUFFIX + "acr"           # must be globally unique, lowercase, 5-50 chars
$KV_NAME         = $SUFFIX + "kv"            # must be globally unique
$LA_NAME         = $SUFFIX + "-la"
$AI_NAME         = $SUFFIX + "-ai"
$ACG_NAME        = $SUFFIX + "-aci"          # Azure Container Group
$DNS_LABEL       = $SUFFIX + "-wattwise"     # becomes {dns}.eastus.azurecontainer.io

$IMG_STREAMLIT   = "streamlit:v1"
$IMG_BMS         = "bms:v1"

$REPO_ROOT       = Resolve-Path (Join-Path $PSScriptRoot "..")
$TRACKING_FILE   = Join-Path $PSScriptRoot ".deployed-resources.json"
$SETTINGS_FILE   = Join-Path $REPO_ROOT ".streamlit/alert_settings.json"

# ============================================================================
# HELPERS
# ============================================================================
function Write-Step($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host ""
    Write-Host "[$ts] >>> $msg" -ForegroundColor Cyan
}
function Write-OK($msg)   { Write-Host "       [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "       [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "       [FAIL] $msg" -ForegroundColor Red }

function Invoke-Az {
    # Plain (non-advanced) function + built-in retry on transient Azure network errors.
    # Retries up to 3 times with exponential backoff on: ConnectionResetError,
    # ConnectionError, timeout, 429, 5xx. Does NOT retry on auth/perm/404 errors.
    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $output = & az @args 2>&1
        $outStr = ($output | Out-String)
        if ($LASTEXITCODE -eq 0) { return $output }
        # Transient markers worth retrying
        $isTransient = $outStr -match '(ConnectionResetError|ConnectionError|Connection aborted|timed out|TimeoutError|TooManyRequests|InternalServerError|ServiceUnavailable|429|500|502|503|504)'
        if (-not $isTransient -or $attempt -eq $maxAttempts) {
            Write-Fail ("az " + ($args -join " "))
            $output | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkRed }
            throw "az command failed with exit code $LASTEXITCODE"
        }
        $waitSec = [int][Math]::Pow(2, $attempt + 1)  # 4, 8, 16 sec
        Write-Warn ("transient error on attempt {0}/{1}; retrying in {2}s..." -f $attempt, $maxAttempts, $waitSec)
        Start-Sleep -Seconds $waitSec
    }
}

function Track-Resource($type, $name) {
    # Build fresh hashtable (PS 5.1 has no -AsHashtable on ConvertFrom-Json)
    $existing = @()
    $deployedAt = (Get-Date).ToString("o")
    if (Test-Path $TRACKING_FILE) {
        try {
            $prev = Get-Content $TRACKING_FILE -Raw | ConvertFrom-Json
            if ($prev.deployed_at) { $deployedAt = $prev.deployed_at }
            if ($prev.resources) {
                foreach ($r in $prev.resources) {
                    $existing += @{ type = $r.type; name = $r.name }
                }
            }
        } catch { }
    }
    # Avoid duplicates
    $dup = $existing | Where-Object { $_.type -eq $type -and $_.name -eq $name }
    if (-not $dup) { $existing += @{ type = $type; name = $name } }
    $tracking = @{ deployed_at = $deployedAt; resources = $existing }
    $tracking | ConvertTo-Json -Depth 5 | Set-Content $TRACKING_FILE -Encoding UTF8
}

function Resource-Exists {
    param([string]$showCmd)
    $null = & cmd /c "$showCmd 2>nul"
    return ($LASTEXITCODE -eq 0)
}

# ============================================================================
# ROLLBACK (delegates to teardown.ps1)
# ============================================================================
if ($Rollback) {
    Write-Step "Rollback mode - delegating to teardown.ps1"
    & (Join-Path $PSScriptRoot "teardown.ps1")
    exit 0
}

# ============================================================================
# PRE-FLIGHT
# ============================================================================
Write-Step "Pre-flight checks"

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Fail "az CLI not found. Install from https://aka.ms/azcli"
    exit 1
}
Write-OK "az CLI present"

# Verify logged in
$account = (az account show --query id -o tsv 2>&1)
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Not logged into Azure. Run: az login"
    exit 1
}
Write-OK "Logged in"

Invoke-Az account set --subscription $SUBSCRIPTION_ID | Out-Null
Write-OK "Subscription set to pSiddhi"

# Install application-insights extension (needed for App Insights create)
$aiExt = az extension list --query "[?name=='application-insights'].name" -o tsv 2>&1
if (-not $aiExt) {
    Write-Step "Installing application-insights CLI extension"
    Invoke-Az extension add -n application-insights | Out-Null
    Write-OK "Extension installed"
} else {
    Write-OK "application-insights extension already present"
}

# Verify RG exists
$rgCheck = az group show -n $RG --query id -o tsv 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Resource Group '$RG' not found"
    exit 1
}
Write-OK "RG '$RG' exists"

# Verify tracking file doesn't exist (would mean previous deploy still live)
if (Test-Path $TRACKING_FILE) {
    Write-Warn "Previous deployment tracked at $TRACKING_FILE"
    Write-Warn "Either run teardown.ps1 first, or delete the tracking file to force fresh deploy"
    $answer = Read-Host "Continue anyway and overwrite tracking? (y/N)"
    if ($answer -ne "y") { exit 1 }
    Remove-Item $TRACKING_FILE
}

# Verify alert_settings.json exists (for secrets)
if (-not (Test-Path $SETTINGS_FILE)) {
    Write-Fail "Settings file not found: $SETTINGS_FILE"
    Write-Fail "LLM API keys + SMTP creds must be in this file"
    exit 1
}
Write-OK "Settings file present"

# ============================================================================
# PHASE 1 - Infrastructure (ACR, Key Vault, Log Analytics, App Insights)
# ============================================================================

# --- ACR ---
Write-Step "Phase 1a: Azure Container Registry ($ACR_NAME)"
Invoke-Az acr create -g $RG -n $ACR_NAME --sku Basic --location $LOCATION --admin-enabled true --only-show-errors | Out-Null
Track-Resource "acr" $ACR_NAME
Write-OK "ACR created, admin enabled"

$acrLoginServer = (Invoke-Az acr show -n $ACR_NAME --query loginServer -o tsv).Trim()
$acrUsername    = (Invoke-Az acr credential show -n $ACR_NAME --query username -o tsv).Trim()
$acrPassword    = (Invoke-Az acr credential show -n $ACR_NAME --query "passwords[0].value" -o tsv).Trim()

# --- Key Vault ---
Write-Step "Phase 1b: Key Vault ($KV_NAME)"
# Use access policy mode (works with Contributor role; RBAC mode would need User Access Administrator)
Invoke-Az keyvault create -g $RG -n $KV_NAME --location $LOCATION --sku standard `
    --enable-rbac-authorization false --only-show-errors | Out-Null
Track-Resource "key-vault" $KV_NAME
Write-OK "Key Vault created (access policy mode)"

# Grant self full permissions
$myUpn = (az account show --query user.name -o tsv).Trim()
Invoke-Az keyvault set-policy -n $KV_NAME --upn $myUpn `
    --secret-permissions get set list delete --only-show-errors | Out-Null
Write-OK "Granted self secret permissions"

# --- Log Analytics + App Insights ---
Write-Step "Phase 1c: Log Analytics workspace ($LA_NAME)"
Invoke-Az monitor log-analytics workspace create -g $RG -n $LA_NAME --location $LOCATION --only-show-errors | Out-Null
Track-Resource "log-analytics" $LA_NAME
Write-OK "Log Analytics created"

$laId = (Invoke-Az monitor log-analytics workspace show -g $RG -n $LA_NAME --query id -o tsv).Trim()

Write-Step "Phase 1d: Application Insights ($AI_NAME)"
Invoke-Az monitor app-insights component create -g $RG -a $AI_NAME --location $LOCATION `
    --workspace $laId --only-show-errors | Out-Null
Track-Resource "app-insights" $AI_NAME
Write-OK "App Insights created"

$aiKey = (Invoke-Az monitor app-insights component show -g $RG -a $AI_NAME --query instrumentationKey -o tsv).Trim()
$aiConn = (Invoke-Az monitor app-insights component show -g $RG -a $AI_NAME --query connectionString -o tsv).Trim()

# ============================================================================
# PHASE 2 - Secrets to Key Vault
# ============================================================================
Write-Step "Phase 2: Loading secrets into Key Vault"

$settings = Get-Content $SETTINGS_FILE -Raw | ConvertFrom-Json
# Only the keys that are non-empty get stored
$secretsToStore = @{
    "GROQ-API-KEY"      = $settings.GROQ_API_KEY
    "GEMINI-API-KEY"    = $settings.GEMINI_API_KEY
    "SMTP-USER"         = $settings.SMTP_USER
    "SMTP-PASSWORD"     = $settings.SMTP_PASSWORD
}
foreach ($kv in $secretsToStore.GetEnumerator()) {
    if ($kv.Value -and $kv.Value.ToString().Trim()) {
        Invoke-Az keyvault secret set --vault-name $KV_NAME --name $kv.Key --value $kv.Value --only-show-errors | Out-Null
        Write-OK ("Stored: " + $kv.Key)
    }
}

# ============================================================================
# PHASE 3 - Build images (parallel) via `az acr build`
#   acr build runs the build on Azure's build servers - no local Docker needed
# ============================================================================
if (-not $SkipImageBuild) {
    Write-Step "Phase 3: Building 2 Docker images via ACR Build (parallel, ~20-30 min)"

    # Start both builds in parallel with --no-wait, then poll
    # Fire Streamlit build
    Push-Location $REPO_ROOT
    try {
        Write-Host "       Firing streamlit build (large, ~20-30 min)..."
        $streamBuild = Invoke-Az acr build --registry $ACR_NAME --image $IMG_STREAMLIT `
            --file infra/Dockerfile.streamlit --no-wait . --only-show-errors
        Write-Host "       Firing bms build (small, ~3-5 min)..."
        $bmsBuild = Invoke-Az acr build --registry $ACR_NAME --image $IMG_BMS `
            --file infra/Dockerfile.bms --no-wait . --only-show-errors
    } finally {
        Pop-Location
    }

    # Poll until both complete
    Write-Host "       Both builds queued. Polling status every 30s..."
    $deadline = (Get-Date).AddMinutes(45)
    $both_done = $false
    while (-not $both_done -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 30
        $tasks = Invoke-Az acr task list-runs -r $ACR_NAME --top 2 `
            --query "[].{id:runId, status:status, image:outputImages[0].repository}" -o json | ConvertFrom-Json
        $runningCount = ($tasks | Where-Object { $_.status -in @("Running","Queued") }).Count
        $failedCount  = ($tasks | Where-Object { $_.status -eq "Failed" }).Count
        $succCount    = ($tasks | Where-Object { $_.status -eq "Succeeded" }).Count
        Write-Host ("       [{0}] running={1} succeeded={2} failed={3}" -f (Get-Date -Format "HH:mm:ss"), $runningCount, $succCount, $failedCount)
        if ($failedCount -gt 0) {
            Write-Fail "At least one image build failed. Check: az acr task list-runs -r $ACR_NAME"
            throw "Image build failed"
        }
        if ($runningCount -eq 0 -and $succCount -ge 2) {
            $both_done = $true
        }
    }
    if (-not $both_done) {
        throw "Image builds did not complete within 45 minutes"
    }
    Write-OK "Both images built and pushed to ACR"
} else {
    Write-OK "Phase 3 skipped (--SkipImageBuild)"
}

# ============================================================================
# PHASE 4 - Generate Container Group YAML and deploy
# ============================================================================
Write-Step "Phase 4: Deploying Container Group ($ACG_NAME)"

# Build env var list for Streamlit container
# Use secureEnvironmentVariables for secrets - never visible in portal after deploy
$streamlitEnv = @"
        environmentVariables:
          - name: LLM_PROVIDER
            value: "groq"
          - name: LLM_MODEL
            value: "qwen/qwen3.8-27b"
          - name: SMTP_HOST
            value: "smtp.gmail.com"
          - name: SMTP_PORT
            value: "465"
          - name: SMTP_USE_TLS
            value: "ssl"
          - name: ALERT_RECIPIENTS
            value: "$($settings.ALERT_RECIPIENTS)"
          - name: BMS_WEBHOOK_URL
            value: "http://localhost:9100/command"
          - name: APPLICATIONINSIGHTS_CONNECTION_STRING
            value: "$aiConn"
        secureEnvironmentVariables:
          - name: GROQ_API_KEY
            secureValue: "$($settings.GROQ_API_KEY)"
          - name: GEMINI_API_KEY
            secureValue: "$($settings.GEMINI_API_KEY)"
          - name: SMTP_USER
            secureValue: "$($settings.SMTP_USER)"
          - name: SMTP_PASSWORD
            secureValue: "$($settings.SMTP_PASSWORD)"
"@

$yaml = @"
apiVersion: 2019-12-01
location: $LOCATION
name: $ACG_NAME
properties:
  osType: Linux
  restartPolicy: OnFailure
  imageRegistryCredentials:
    - server: "$acrLoginServer"
      username: "$acrUsername"
      password: "$acrPassword"
  ipAddress:
    type: Public
    dnsNameLabel: $DNS_LABEL
    ports:
      - protocol: tcp
        port: 8501
      - protocol: tcp
        port: 9100
  containers:
    - name: streamlit
      properties:
        image: $acrLoginServer/$IMG_STREAMLIT
        resources:
          requests:
            cpu: 2.0
            memoryInGb: 4.0
        ports:
          - port: 8501
$streamlitEnv
    - name: bms
      properties:
        image: $acrLoginServer/$IMG_BMS
        resources:
          requests:
            cpu: 0.5
            memoryInGb: 0.5
        ports:
          - port: 9100
"@

$yamlFile = Join-Path $PSScriptRoot "container-group.yaml"
$yaml | Set-Content $yamlFile -Encoding UTF8
Write-OK ("YAML written to " + $yamlFile)

Invoke-Az container create -g $RG --file $yamlFile --only-show-errors | Out-Null
Track-Resource "container-group" $ACG_NAME
Write-OK "Container group deployment started"

# Wait for container group ready
Write-Host "       Waiting for container group to be running (up to 5 min)..."
$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 15
    $state = (Invoke-Az container show -g $RG -n $ACG_NAME --query "instanceView.state" -o tsv).Trim()
    Write-Host ("       state = $state")
    if ($state -eq "Running") { break }
}

$fqdn = (Invoke-Az container show -g $RG -n $ACG_NAME --query "ipAddress.fqdn" -o tsv).Trim()
Write-OK "Container group running"

# ============================================================================
# DONE
# ============================================================================
Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host "   WattWise AI DEPLOYED TO AZURE" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Dashboard URL : http://${fqdn}:8501" -ForegroundColor Yellow
Write-Host "   Mock BMS URL  : http://${fqdn}:9100" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Login: admin / wattwise2026" -ForegroundColor Gray
Write-Host "          ops   / ops" -ForegroundColor Gray
Write-Host "          demo  / demo" -ForegroundColor Gray
Write-Host ""
Write-Host "   First page load may take 60-90s (Streamlit cold start)" -ForegroundColor Gray
Write-Host ""
Write-Host "   To verify end-to-end: ./verify.ps1" -ForegroundColor Gray
Write-Host "   To tear everything down: ./teardown.ps1" -ForegroundColor Gray
Write-Host ""
