# Local Setup — Podman + Azure (new laptop)

Rebuild of the WattWise AI development environment on a fresh Windows 11 machine,
using **Podman instead of Docker**.

Companion to [`PROJECT_BLUEPRINT.md`](../PROJECT_BLUEPRINT.md). The blueprint says
*what* is being built; this says *how to run it here*.

---

## 0. What happened to the source code (resolved)

The laptop transfer brought the scaffold but **none of the ~30 implemented source
files**. `.git/index` came across, `.git/objects` did not — git listed every file
as staged (`AD` = added-to-index, deleted-from-disk) while `.git` sat at 0.01 MB
with zero objects and `git fsck` reported `missing blob` for all of them. There
were never any local commits.

**Recovered from GitHub** (`origin` = https://github.com/Arxnnan/wattwise-ai) via
`git reset --hard origin/main`, restoring commit `96d069c`:

> *Phase 2 complete: Cost domain, LSTM-AE, XGBoost optimizer, Gemini narratives,
> Evidently drift, 5-view dashboard, 57 tests*

The project is therefore **Phase 2 complete** — far past the "Week 4, Day 1" that
`PROJECT_BLUEPRINT.md` §9 still claims. **Treat the blueprint's status markers as
stale.** The repo history is the source of truth:

| Commit | Milestone |
|---|---|
| `ba7e63c` | Initial scaffold |
| `101a343` | Phase 1 — IoT simulator, ingestion pipeline, AI core, dashboards, 37 tests |
| `96d069c` | Phase 2 — cost domain, LSTM-AE, XGBoost optimizer, narratives, drift, 5 views, 57 tests |

### Verified after restore

| Check | Result |
|---|---|
| `pytest` | **57/57 pass** |
| Coverage (`ml` + `ingestion` + `triggers`) | **60%** — below the RFP's 80% gate, see below |
| E2E: simulator → Mosquitto → pipeline → ClickHouse | **PASS** — 162 readings, 3 facilities × 3 domains, 0 invalid |
| Azurite blob round-trip via `azure-storage-blob` | **PASS** |

Coverage gap — three modules are at **0%**, and they are the whole shortfall:

| Module | Statements | Covered |
|---|---|---|
| `ingestion/pipeline.py` | 58 | 0% |
| `ml/drift_monitor.py` | 84 | 0% |
| `triggers/handler.py` | 49 | 0% |

Covering those three is what gets you from 60% to the ≥80% gate. Note that
`pipeline.py` having no tests is exactly why the paho-mqtt 2.x break in §3 went
unnoticed — the suite was green while Layer 1 was broken at runtime.

> **Schema note.** The authentic `analytics/clickhouse/001_init_schema.sql` uses a
> `ts` column (not `timestamp`) and an `anomaly_events` table (not `anomalies`),
> with no materialized views. All of `ml/` and `ingestion/` is written against it.

---

## 1. Toolchain status

| Tool | Required | On this machine | Notes |
|---|---|---|---|
| Python 3.11 | 3.11.x | ✅ 3.11.9 | Installed via `winget install Python.Python.3.11`. **Not** 3.14 — see blueprint §4 |
| Python 3.14 | — | ✅ 3.14.6 | Present but unused by this project |
| Podman | 5+ | ✅ 6.0.2 | Replaces Docker Desktop |
| podman-compose | 1.x | ✅ 1.6.0 | `pip install podman-compose` |
| Azure CLI | 2.5x+ | ✅ 2.88.0 | |
| `azure-iot` CLI extension | latest | ✅ 0.30.0 | `az extension add --name azure-iot` — required for every `az iot hub …` command |
| Azure Functions Core Tools | v4 | ✅ 4.13.0 | Installed via **npm**, not winget (see §6) |
| Azurite (Blob emulator) | latest | ✅ container | Runs in `compose.yaml`, not installed on the host |
| Node.js | 18+ | ✅ 24.18.0 | |
| Git | 2.x | ✅ 2.55.0 | |

### Azure local coverage — what exists and what doesn't

| Azure service | Local equivalent | Status |
|---|---|---|
| Functions runtime | Azure Functions Core Tools v4 | ✅ installed |
| Blob Storage | Azurite (official MS emulator) | ✅ container |
| IoT Hub | **none — Microsoft ships no Hub emulator** | Mosquitto stand-in |
| Communication Services (email) | Mailpit | ✅ container |
| Monitor / Cost Management | none | cloud-only |

### Optional GUI tools (not installed)

Not required to run anything; install only if you want the click-through UIs.

```powershell
winget install Microsoft.Azure.StorageExplorer   # browse Blob containers
winget install Microsoft.Azure.IoTExplorer       # watch IoT Hub device telemetry live
winget install Microsoft.PowerBI                 # dashboard views 3 & 5
```

---

## 2. Podman: the local stack

The old `docker-compose.yml` has been replaced by [`compose.yaml`](../compose.yaml)
— the vendor-neutral Compose Specification filename, read by both podman-compose
and docker compose.

```powershell
podman machine start            # once per boot
podman compose up -d            # start the stack
podman compose ps               # what's running
podman compose logs -f grafana  # tail one service
podman compose down             # stop (keeps volumes)
podman compose down -v          # stop AND wipe data
```

### Services

| Service | Container | Port | Stands in for | Credentials |
|---|---|---|---|---|
| Mosquitto | `wattwise-mosquitto` | 1883 (MQTT), 9001 (WS) | **Azure IoT Hub** | anonymous |
| ClickHouse | `wattwise-clickhouse` | 8123 (HTTP), 9000 (native) | ClickHouse on the B1s VM | `wattwise` / `wattwise_dev` |
| Grafana | `wattwise-grafana` | 3001 → 3000 | Grafana on the B1s VM | `admin` / `wattwise_dev` |
| Mailpit | `wattwise-mailpit` | 1025 (SMTP), 8025 (UI) | **Azure Communication Services** | none |
| Azurite | `wattwise-azurite` | 10000/10001/10002 | **Azure Blob Storage** | `devstoreaccount1` (well-known key) |
| Ollama | `wattwise-ollama` | 11434 | local LLM fallback | none — **opt-in**, see below |

### Azurite — local Azure Blob Storage

Microsoft's official Storage emulator. `azure-storage-blob` talks to it exactly as
it would to a real storage account, so the telemetry-archive and ml-artefacts
containers that [`infra/provision_azure.ps1`](../infra/provision_azure.ps1) creates
in Azure can be developed against offline. Add to `.env`:

```
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
```

That account name and key are the fixed, publicly-documented Azurite development
credentials — they are not secrets and are identical on every machine.

> **There is no local Azure IoT Hub emulator.** Microsoft does not ship one
> (`iotedgehubdev` emulates IoT *Edge* modules, not a Hub). Mosquitto is the
> stand-in, which is why `compose.yaml` runs it — verified end-to-end with the
> real simulator and ingestion pipeline.

Grafana is on **3001** because the container's 3000 is remapped; port 3000 on this
machine is already taken by an unrelated Grafana.

Ollama is behind a compose profile (it is the heaviest service and the blueprint
scopes it to the dev laptop only):

```powershell
podman compose --profile llm up -d
podman exec -it wattwise-ollama ollama pull llama3.1:8b
```

### What differs from the Docker version

1. **Image names are fully qualified** (`docker.io/library/eclipse-mosquitto:2.0`).
   Podman does not assume Docker Hub; an unqualified name triggers an interactive
   registry-selection prompt that hangs any non-interactive shell.
2. **Bind-mount sources must exist first.** Docker silently creates a missing host
   directory; Podman errors out. These files were missing from the repo and have
   been added:
   - `infra/mosquitto/mosquitto.conf`
   - `analytics/clickhouse/01_schema.sql`
   - `dashboards/grafana/provisioning/datasources/clickhouse.yml`
   - `dashboards/grafana/provisioning/dashboards/dashboards.yml`
3. **MailHog → Mailpit.** `mailhog/mailhog` is archived and unmaintained; Mailpit
   is the drop-in successor with the same SMTP:1025 / UI:8025 ports.
4. **Healthchecks use the shell form, not `["CMD", ...]`.** podman-compose passes
   the exec-form array through verbatim, so the container receives a literal
   `CMD` argument and the check fails with `Error: Unknown option 'CMD'` — the
   service runs fine but is permanently marked `(unhealthy)`, which then stalls
   anything with `depends_on: condition: service_healthy`. A plain string is
   `CMD-SHELL` per the Compose Spec and works under both engines.
5. **`docker-compose.yml` was deleted.** podman-compose reads *both* it and
   `compose.yaml` and tries to **merge** them, which fails with
   `ValueError: can't merge value of [test] of type str and list` once the two
   disagree. Keep exactly one compose file.
6. Named volumes are Podman volumes — `podman volume ls`, not `docker volume ls`.

### ⚠️ Known issue: `localhost` ports don't reach the containers

Container ports publish **inside** the WSL2 VM that backs Podman, and this machine's
WSL localhost relay is currently wedged — nothing is listening on the Windows side
(`Get-NetTCPConnection -State Listen -LocalPort 8123` returns nothing). This affects
*every* container on the machine, not just this project.

**Works right now** — reach services on the VM's IP:

```powershell
$ip = (wsl -d podman-machine-default -- ip -4 -o addr show eth0) -replace '.*inet\s+([0-9.]+)/.*','$1'
curl "http://${ip}:8123/ping"     # ClickHouse  → Ok.
start "http://${ip}:3001"         # Grafana
start "http://${ip}:8025"         # Mailpit
```

That IP changes when WSL restarts, so re-run the first line after a reboot.

**Permanent fix** — restart the WSL subsystem. This restarts *all* WSL distros and
every container on the machine, so pick your moment:

```powershell
wsl --shutdown
podman machine start
podman compose up -d
```

If it wedges again, switch WSL to mirrored networking, which forwards localhost
reliably. Create `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

then `wsl --shutdown`. Mirrored mode is machine-wide — it changes networking for
every WSL distro, so verify your other projects still behave.

---

## 3. Python environment

The `.venv` that came across from the old laptop was **broken** — it recorded the
old path (`…\Psiddhi\sem 4\wattwise-ai`) and pointed at a Python 3.11 install that
does not exist here. It has been deleted and rebuilt.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Two dependency conflicts were fixed in `requirements.txt`

Both were real defects — the file as written could not be installed by any
resolver, on any machine.

| Was | Problem | Now |
|---|---|---|
| `azure-iot-device>=2.13` + `paho-mqtt>=2.1` | Mutually exclusive: `azure-iot-device` (every 2.13–2.14 release) pins `paho-mqtt<2.0.0` → `ResolutionImpossible`. | `azure-iot-device` removed, `paho-mqtt>=2.1` kept |
| `pycaret>=3.3` | Every `pycaret` 3.3.x pins `pandas<2.2.0`, which cannot co-exist with `pandas>=2.2` or the numpy 2.x that darts / tensorflow / prophet resolve to. | Moved to `requirements-training.txt` |

#### Why paho-mqtt wins and azure-iot-device yields

This one has a trap. Pinning `paho-mqtt<2.0` to satisfy `azure-iot-device` makes
pip happy and **breaks Layer 1 at runtime**:

```
AttributeError: module 'paho.mqtt.client' has no attribute 'CallbackAPIVersion'
```

Both [`ingestion/simulator.py`](../ingestion/simulator.py) (line 161) and
[`ingestion/pipeline.py`](../ingestion/pipeline.py) (line 59) call
`mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, ...)` — an API that only exists in
paho-mqtt **2.x**. Meanwhile `azure-iot-device` is **not imported anywhere** in the
codebase; local ingestion goes through Mosquitto, not IoT Hub.

So the working code wins and the unused SDK goes. When the real IoT Hub device
client is written (Wk 5 / deployment), either install it in a separate environment
or port those two call sites to the paho 1.x callback API.

The full test suite passes under **both** pins — `pipeline.py` has no tests, so
nothing caught this. Fixing that coverage gap (§0) would have.

PyCaret is **not dropped** — it moved to the training side of the split the
blueprint already defines (§4: training on Colab, inference locally). See
[`requirements-training.txt`](../requirements-training.txt). It stays part of the
delivered stack for the RFP tool list.

---

## 4. Environment file

```powershell
Copy-Item .env.example .env
```

The ClickHouse block already matches the compose defaults and needs no edit. Fill
in the rest as you reach each week:

| Variable | Needed by | When |
|---|---|---|
| `GEMINI_API_KEY` | narrative generation | Wk 14 — https://aistudio.google.com |
| `HUGGINGFACE_API_TOKEN` | LLM fallback | Wk 14 — https://huggingface.co/settings/tokens |
| `IOT_HUB_*` | real IoT Hub ingestion | Wk 5 — after the hub is provisioned |
| `AZURE_STORAGE_CONNECTION_STRING` | model artefacts | Wk 8 |
| `ACS_*`, `TWILIO_*` | alerting | Wk 14 |

`.env` is gitignored. Never commit it.

---

## 5. Azure

### Log in

```powershell
az login
az account set --subscription 23724963-04db-44e4-8858-55c4bcd63dc8
az account show --output table
```

Not currently logged in on this machine — do this before running any `az` command
or `infra/provision_azure.ps1`.

### What gets provisioned

[`infra/provision_azure.ps1`](../infra/provision_azure.ps1) creates 3 of the 6
resources into the pre-created resource group `rg-pSiddhi3.0-2026-01-sem4-Arunn`:

| # | Resource | Script | Notes |
|---|---|---|---|
| 1 | Storage Account `wattwiseblob2026` + 2 containers | ✅ | telemetry archive + ML artefacts |
| 2 | B1s Ubuntu VM `wattwise-vm` | ✅ | opens 8123 / 3001 / 8000 / 8501 |
| 3 | Functions App `wattwise-functions` | ✅ | Python 3.11, Functions v4, Linux |
| 4 | **IoT Hub** | ❌ | script comment says L&D creates it — needs Contributor |
| 5 | Budget alert ₹1,200 | ❌ | script says L&D already configured it |
| 6 | Azure Communication Services | ❌ | not scripted; Wk 14 |

Everything is Free Tier. Committed cloud cost: ₹0.

> **Nothing needs to be downloaded to run Azure locally** beyond the CLI, the
> `azure-iot` extension, and Functions Core Tools — all three are installed. The
> Azure *SDKs* (`azure-iot-device`, `azure-functions`, `azure-storage-blob`,
> `azure-identity`) come from `requirements.txt` into the venv.

### You can build weeks 4–8 with no Azure at all

The compose stack replaces every cloud dependency for local development:
Mosquitto for IoT Hub, local ClickHouse for the VM's ClickHouse, Mailpit for ACS.
Provision Azure when you need the real ingestion path (Wk 5) or the deployment
target (Wk 15).

---

## 6. Gotchas hit during this setup

- **Functions Core Tools via winget fails without elevation.** The MSI needs UAC;
  a non-elevated silent install returns exit code 1602 ("user cancelled"). The npm
  route avoids the MSI entirely:
  `npm install -g azure-functions-core-tools@4 --unsafe-perm true`
- **`podman compose` needs a provider on PATH.** Podman shells out to
  `podman-compose` or `docker-compose`; with neither it fails with
  *"looking up compose provider failed"*. `pip install podman-compose` puts the exe
  in `%APPDATA%\Roaming\Python\Python314\Scripts`, which is **not** on PATH by
  default — that directory has been appended to the user PATH.
- **`podman machine list` reports stale resources.** It showed 2 GiB / 7 CPUs;
  the machine actually has 15 GiB / 14 CPUs / 942 GB free. Trust `wsl -d
  podman-machine-default -- free -h` instead. No resize was needed.
- **First `podman compose up` may hit `tls: internal error`** pulling from Docker
  Hub's CDN when several images pull in parallel. It is transient — re-run.
