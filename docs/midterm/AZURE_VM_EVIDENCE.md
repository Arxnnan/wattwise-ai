# B1s VM — Provisioning Evidence (then deprovisioned)

Captured 2026-09-03 as proof the RBAC fix (Network Contributor grant) actually
resolved the VM blocker documented in `UC01_APPEAL.md` / `PROJECT_BLUEPRINT.md`
§11. The VM was created, verified running with a real public IP, then
**deleted immediately afterward** to avoid ongoing cost — this subscription is
confirmed Pay-As-You-Go (`quotaId: PayAsYouGo_2014-09-01`, `spendingLimit: Off`),
not a free trial, so nothing left running here is actually free.

- VM: `wattwise-vm`, Standard_B1s, Ubuntu 22.04 LTS, `eastus`
- Public IP: `172.173.216.104` (Standard SKU — Basic SKU was blocked by a
  subscription-wide quota of 0, a separate, later-hit limit from the RBAC gap)
- Created: 2026-09-03T07:21:13Z · Deallocated: 2026-09-03T07:24:28Z (~5 min runtime)
- Provisioning state: `Succeeded` on every resource (VM, VNet, NSG, Public IP, NIC)

Full CLI transcript (VM details, public IP, power state, resource group
listing) is in this session's evidence capture — reproducible any time by
re-running `infra/provision_azure.ps1` now that Network Contributor is
granted; it will succeed cleanly.

**To bring the VM back for the actual demo:** re-run
`.\infra\provision_azure.ps1` (or just the VM section) — Storage and
Functions already exist and will be left alone; the VM section will
recreate cleanly since it was fully deleted, not just deallocated.
