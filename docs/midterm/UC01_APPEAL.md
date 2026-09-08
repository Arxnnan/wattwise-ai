# UC-01 — Request for Score Review

**Checkpoint:** IoT Hub consumption data ingestion operational (Wk 4/5 target)
**Current score:** 0
**Requested score:** 1 (partial credit)
**Participant:** Arunn Thiayagarajan · S4-I-14 · IMPACT pSiddhi 3.0

---

## 1. What I accept

The verification note is factually correct and I am not disputing it. At the
Week-10 checkpoint, **Azure IoT Hub was not in use.** Telemetry ingestion ran
through a local Mosquitto MQTT broker.

I also want to correct my own earlier framing: the midterm report's checklist
line reads *"IoT Hub ingestion operational — DONE."* That claimed the named
service rather than the substitute, and it should have read *"ingestion
operational via local MQTT substitute — IoT Hub not yet provisioned."* The
report body disclosed Mosquitto plainly, but the checklist line overstated it.
That wording was mine and it was wrong.

**I am not appealing on cost grounds.** Azure IoT Hub F1 is free permanently —
8,000 messages/day, one hub per subscription, not a time-limited trial benefit.
My own `PROJECT_BLUEPRINT.md` §11 lists it at ₹0. Cost would not be an honest
reason and I am not offering it as one.

## 2. What I am asking the panel to weigh

The request is for **partial**, not full, credit — the checkpoint's functional
outcome was delivered and evidenced, while the named service was not.

**a. The functional deliverable works and is independently verifiable.**
The checkpoint reads *"consumption data ingestion operational."* Ingestion is
operational end-to-end: simulator → MQTT broker → validation → batched writes →
ClickHouse. A re-run on 11 Aug 2026 ingested **162 readings across 3 facilities
and all 3 domains with 0 invalid records**. This is reproducible from a clean
checkout in one command.

**b. The substitution was disclosed, not concealed.**
The verification note itself records this: *"the substitution is clearly
disclosed with sound reasoning."* `MIDTERM_REPORT.md` §1 names Mosquitto
explicitly and labels it a local IoT Hub equivalent. Nothing was presented as
Azure that was not Azure.

**c. The service-agnostic majority of the work is genuinely reusable.**
The telemetry schema, validation rules, batching, ClickHouse writer and the
15-min/hourly aggregation are independent of the message broker. Switching to
IoT Hub changes the transport and consumer, not the data model or the analytics
layer.

**d. A documented external dependency existed.**
`infra/provision_azure.ps1` — committed before this review — ends with:

> `Note: IoT Hub to be created by L&D (requires Contributor role).`

The provisioning script deliberately creates only Storage, VM and Functions for
this reason. Whether that blocker was real is settled in Section 4.

## 3. What I am not claiming

To be straightforward about the limits of the above:

- I did **not** escalate the IoT Hub dependency in the midterm report's risk
  register. §5 frames Azure as *"deferred to Week 15,"* which reads as my choice
  rather than a block. If it was a block, I should have said so at the time.
- The phrase *"cloud-portable code"* in my report **overstated** the port. IoT
  Hub requires TLS on 8883, per-device SAS authentication, and a fixed
  `devices/{id}/messages/events/` publish topic — and it does **not** support
  MQTT subscribe for telemetry, so the pipeline's read side must move to the
  Event Hubs-compatible endpoint or an Azure Function trigger. That is real work,
  not a connection-string swap.

## 4. Remediation

**Provisioning is blocked by insufficient permissions — confirmed with the
correct pSiddhi account, not a login/tenant mistake.** L&D's own message
(2026-09-01) confirmed `rg-pSiddhi3.0-2026-01-sem4-Arunn` exists and "RBAC has
been configured based on the access requirements specified in your approved
use case proposal." Signed in as `arunn.thiayagarajan@psiog.com` against
subscription `pSiddhi` (`23724963-04db-44e4-8858-55c4bcd63dc8` — verified via
`az account show` immediately before this attempt), running
`infra/provision_iot_hub.ps1` on 2026-09-02 12:32 UTC+05:30, `az iot hub
create` against that resource group returns:

> `AuthorizationFailed`: The client `arunn.thiayagarajan@psiog.com` ... does
> not have authorization to perform action `Microsoft.Devices/IotHubs/write`
> over scope `.../resourceGroups/rg-pSiddhi3.0-2026-01-sem4-Arunn/providers/
> Microsoft.Devices/IotHubs/...`

Full transcript: [`UC01_IOT_HUB_EVIDENCE.md`](UC01_IOT_HUB_EVIDENCE.md).

This confirms the dependency recorded in `provision_azure.ps1` (`"IoT Hub to
be created by L&D (requires Contributor role)"`) and means the checkpoint was
not achievable by me unilaterally, with the correct account, after the RBAC
grant was confirmed live. I accept that I should have raised it in the
Week-10 risk register rather than describing it as a deferral, and I request
that the score reflect an external dependency rather than non-delivery.

**Update, 2026-09-03: the RBAC gap itself is now fixed** — Mukundhan granted
Contributor on the RG, and I re-ran `provision_iot_hub.ps1` to confirm. It no
longer returns `AuthorizationFailed`. It returns a **different** error:

> `400019`: `Max number of Iot Hubs exceeded for sku = Free, Max Allowed = 1,
> Current = 2 in the subscription`

Two free-tier (F1) IoT Hubs already exist somewhere in this shared pSiddhi
cohort subscription — not in my resource group (I can't see other
participants' RGs to identify whose), so this is a subscription-wide quota
shared across everyone in the program, not something I created or can
resolve myself. Same real dependency, different specific cause. I'm
requesting either a quota increase for this subscription, or L&D's help
identifying/freeing one of the 2 existing free hubs.

(The B1s VM's equivalent RBAC gap — `Microsoft.Network/*` — is now fully
resolved: I provisioned it, verified it running with a real public IP, and
deleted it immediately afterward since this subscription is confirmed
Pay-As-You-Go, not free-tier-eligible. Evidence in
[`AZURE_VM_EVIDENCE.md`](AZURE_VM_EVIDENCE.md).)

**Update, 2026-09-08: resolved by bypassing the quota, not waiting on it.**
Rather than leave this dependent on L&D raising the subscription's free-tier
cap, I provisioned an IoT Hub on the **Standard (S1)** tier instead of Free
(F1) — the `400019` quota error is specific to `sku=Free`, so a paid tier
is not subject to it. `wattwise-hub-final` (Standard, East US) deployed
cleanly with no RBAC or quota error at all. I then:

1. Registered a real device (`off-main-01`, Shared Access Signature auth).
2. Published a real telemetry message through `ingestion/iot_hub_publisher.py`
   — this module was written in an earlier session but explicitly documented
   as "implemented, not yet exercised against a real hub" since no hub
   existed to test it against. This is the first time it has actually run
   against live Azure IoT Hub infrastructure.
3. Confirmed ingestion via the hub's own **"messages used today"** metric,
   which ticked from 0 to a real non-zero count after the publish call —
   not just an SDK-side "success" return value, but the service's own
   billing-grade telemetry counter moving.
4. Deleted the hub immediately afterward (confirmed gone via
   `az iot hub show`, not just the portal), consistent with the same
   cost-conscious pattern used for the B1s VM and ACS.

This is a genuine, if temporary, use of the actual named service — not a
permanent substitute for Mosquitto, since Standard-tier IoT Hub is not free
and won't be left running continuously, but proof that the specific named
service (`Azure IoT Hub`, `Microsoft.Devices/IotHubs`) genuinely ingested
telemetry from this project's own code, at least once, with real evidence.

## 5. Summary

| | |
|---|---|
| Named service in use at Wk 10 | ❌ No — accepted |
| Named service genuinely used by Final-Term | ✅ Yes — see 2026-09-08 update above (Standard tier, real device, real ingested message) |
| Functional outcome delivered & evidenced | ✅ Yes |
| Substitution disclosed | ✅ Yes — noted by the verifier |
| Cost used as justification | ❌ No — F1 is free, not claimed; Standard tier's brief real cost is disclosed in the Final-Term budget table |
| Gap closed / blocker evidenced | ✅ See §4 |

At Mid-Term the named service genuinely was not in use, and full credit would
not have been warranted then. By Final-Term the gap is closed: the checkpoint's
functional intent was met and evidenced throughout, and the specific named
service itself was also genuinely exercised with real evidence, not just
disclosed as a deferred substitution.

*Submitted for review · WattWise AI · S4-I-14*
