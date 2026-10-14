# WattWise AI - Full Azure Deployment

End-to-end deployment of WattWise AI to Azure.

## What gets deployed

| Resource | Purpose | Approx 2-hr cost |
|---|---|---|
| Azure Container Registry (Basic) | Holds Docker images | ~₹1 |
| Key Vault (Standard) | Stores API keys + SMTP creds | ~₹0 |
| Log Analytics workspace | Backs App Insights | ~₹2 |
| Application Insights | Observability | ~₹5 |
| Container Group (2 containers) | Streamlit dashboard + Mock BMS | ~₹13 |
| **Total** | | **~₹20-30** |

## Prerequisites

- Azure CLI installed and logged in (`az login`)
- Contributor role on `rg-pSiddhi3.0-2026-01-sem4-Arunn`
- `.streamlit/alert_settings.json` with valid `GROQ_API_KEY` + Gmail SMTP creds

## Usage

```powershell
cd infra

# Deploy everything (~60-90 min, mostly image builds)
./deploy.ps1

# Verify deployed services are responding
./verify.ps1

# Teardown (reads tracking file, deletes exact resources)
./teardown.ps1
```

## Flags

- `./deploy.ps1 -SkipImageBuild` - redeploy container group only (if images already in ACR)
- `./deploy.ps1 -Rollback` - alias for `./teardown.ps1`

## Deployment phases

1. **Pre-flight** - verifies CLI, extensions, RG, settings file (~30s)
2. **Infrastructure** - ACR + Key Vault + Log Analytics + App Insights (~5 min)
3. **Secrets** - loads LLM keys + SMTP creds into Key Vault (~30s)
4. **Image build** - `az acr build` runs the Dockerfiles on Azure's build servers in parallel (~25 min for first build, ~5 min subsequently)
5. **Container Group** - deploys YAML spec with 2 containers in 1 group (~5 min)
6. **Done** - prints Streamlit + Mock BMS URLs

## Container group architecture

Both containers run in a single Container Group:
- They share the same network namespace (both reachable via `localhost`)
- Streamlit calls Mock BMS at `http://localhost:9100`
- Public IP exposes both ports (8501 for dashboard, 9100 for BMS console)
- DNS: `http://<DNS_LABEL>.eastus.azurecontainer.io`

## Tracking file

`.deployed-resources.json` is written during deploy and read during teardown. It records every resource name created, so teardown deletes exactly what was deployed - never a wildcard match.

## Security notes

- Streamlit login credentials (admin/wattwise2026, ops/ops, demo/demo) are the demo defaults
- Mock BMS endpoint is public (no auth) - consider adding `BMS_AUTH_TOKEN` for production
- Secrets stored as `secureEnvironmentVariables` on the container group - not visible in portal after deploy
- Secrets also mirrored into Key Vault for audit

## Troubleshooting

**Image build fails** → check `az acr task list-runs -r <acr-name>`, inspect `az acr task logs --registry <acr-name> --run-id <id>`

**Container group stuck in Pending** → check `az container show -g <rg> -n <acg-name> --query "containers[].instanceView.currentState"`

**Streamlit returns 503** → first boot takes 60-90s to load ML models. Wait a minute.

**Email alerts don't fire** → Azure egress sometimes blocks port 465. Check logs with `az container logs -g <rg> -n <acg-name> --container-name streamlit`. If blocked, migrate to ACS.

## Teardown behaviour

The teardown script:
1. Reads `.deployed-resources.json`
2. Prompts for confirmation (type 'yes')
3. Deletes in reverse dependency order (ACG → AI → LA → KV → ACR)
4. Purges Key Vault so the name is immediately re-usable
5. Removes the tracking file on success
