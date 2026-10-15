# Build-time optimization: split base + app layers

The original `Dockerfile.streamlit` reinstalls torch, tensorflow, chronos,
darts, prophet, xgboost, mlflow, evidently, etc. on every code change — a
~13-minute build that is 95% dependency install and 5% source copy.

`Dockerfile.base` + `Dockerfile.streamlit.v2` split that into two layers:

| Layer | Rebuild trigger | Build time |
|---|---|---|
| `wattwise-base:v1` (Dockerfile.base) | `requirements.txt` changes | ~8-10 min |
| `streamlit:vN` (Dockerfile.streamlit.v2) | any `.py` change | ~60-90 s |

The base image also pulls **CPU-only torch wheels** (~400 MB smaller than
default) and uses **uv** instead of pip for the resolve (~3x faster).

## Workflow

```powershell
# First time, or when requirements.txt changes:
az acr build -r <acr> -t wattwise-base:v1 -f infra/Dockerfile.base .

# For any code change thereafter:
az acr build -r <acr> -t streamlit:v3 -f infra/Dockerfile.streamlit.v2 .
# Then redeploy container group (az container delete + create).
```

## When to bump the base version

- `requirements.txt` changed → `wattwise-base:v2` + update the FROM line in
  `Dockerfile.streamlit.v2`.
- Python version bumped → same.
- A pinned dep known to leak CVEs → same.

Otherwise, keep reusing `wattwise-base:v1`.

## Backwards compat

The legacy `Dockerfile.streamlit` is retained and still works. Both paths
produce functionally-identical images; the v2 path just skips redundant
pip work.
