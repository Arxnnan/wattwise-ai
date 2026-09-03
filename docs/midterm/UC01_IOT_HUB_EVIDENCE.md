=== WattWise AI - IoT Hub provisioning ===
Attempted at: 2026-09-03 12:47:25 UTC+05:30
Resource group: rg-pSiddhi3.0-2026-01-sem4-Arunn

Signed in as : arunn.thiayagarajan@psiog.com
Subscription : pSiddhi (23724963-04db-44e4-8858-55c4bcd63dc8)

[1/4] Creating IoT Hub 'wattwise-hub-4298' (SKU F1, FREE)...

RESULT: FAILED
Azure returned:
az : ERROR: (400019) Max number of Iot Hubs exceeded for sku = Free, Max Allowed = 1, Current = 2 in the subscription 
Id: 23724963-04db-44e4-8858-55c4bcd63dc8. If you contact a support representative please include this correlation 
identifier: 7ebd3d3b-f6ee-4c79-8fb8-df99e3cdd4f5, timestamp: 2026-09-03 07:18:18Z, errorcode: IH400019.
At C:\Users\arunn.thiayagarajan\sem 4\wattwise-ai\infra\provision_iot_hub.ps1:52 char:14
+ $createOut = az iot hub create `
+              ~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (ERROR: (400019)...code: IH400019.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
Code: 400019
Message: Max number of Iot Hubs exceeded for sku = Free, Max Allowed = 1, Current = 2 in the subscription Id: 
23724963-04db-44e4-8858-55c4bcd63dc8. If you contact a support representative please include this correlation 
identifier: 7ebd3d3b-f6ee-4c79-8fb8-df99e3cdd4f5, timestamp: 2026-09-03 07:18:18Z, errorcode: IH400019.


