# api/ — Model Inference Service

**Built in:** Weeks 8, 14

Lightweight FastAPI service that serves trained models for inference. Runs on the Azure B1s VM (training happens separately on Colab).

## Will contain
- `main.py` — FastAPI app
- `routers/forecast.py` — `/forecast` → 24h demand prediction
- `routers/anomaly.py` — `/anomaly/score` → anomaly verdict
- `routers/peak.py` — `/peak/recommend` → load-shed sequence
- `routers/narrate.py` — `/narrate` → Gemini/HF narrative
- `models/` — loaded model artefacts (pulled from Azure Blob; gitignored)

## Run locally
```powershell
uvicorn api.main:app --reload --port 8000
```

## Notes
Models load from Azure Blob at startup. Falls back to Hugging Face Inference API when Gemini quota is exhausted; Ollama for local dev.
