# ml/ — AI / ML Core (Layer 3)

**Built in:** Weeks 7–8, 11, 13

The engine of the product. Remove it and WattWise AI does not function.

## Components
| Module | Technique | Target | Week |
|---|---|---|---|
| `forecasting/` | Chronos (zero-shot) + Darts ensemble (N-BEATS, TFT, XGBoost, Prophet) + Optuna | MAPE ≤ 8% | Wk 8 |
| `anomaly/` | PyOD ensemble (IF + COPOD + ECOD) → LSTM Autoencoder → Evidently drift | F1 ≥ 0.88 | Wk 7, 11 |
| `peak/` | XGBoost load-ranking regressor (explainable shed sequence) | — | Wk 13 |
| `narrative/` | Gemini 2.5 Flash + HF Inference API fallback + Ollama (local dev) | — | Wk 14 |
| `notebooks/` | Colab training notebooks (T4 GPU) — export artefacts to Azure Blob | — | Wk 7–8 |

## Training vs inference
Training runs on **Google Colab free tier**. Inference runs on the **Azure B1s VM** via the FastAPI service in [`../api/`](../api/). MLflow tracks every experiment.

## The 3 mandated AI scenarios
peak demand · anomalous consumption · optimization opportunity — each covered by real ML (see `PROJECT_BLUEPRINT.md` §7).
