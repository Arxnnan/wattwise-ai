# infra/ — Azure Provisioning

**Built in:** Weeks 4, 15

Scripts to provision the Azure footprint — all Free Tier, total committed cost ₹0.

## Will contain
- `provision.ps1` — az CLI provisioning in order (RG → IoT Hub → B1s VM → Blob → Functions → budget alert)
- `bicep/` — optional infra-as-code templates
- `teardown.ps1` — clean removal of all resources

## Provisioning order (Wk 4)
1. `az group create`
2. `az iot hub create` (F1 free SKU)
3. `az vm create` (B1s, Ubuntu)
4. `az storage account create` + container
5. `az functionapp create`
6. `az monitor` budget alert at **₹1,200**

## Cost guardrail
Budget alert at ₹1,200 (ceiling ₹2,500). B1s VM stopped nightly to conserve free-tier hours.
