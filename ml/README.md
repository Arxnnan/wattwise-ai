# ml/ — AI / ML Core (Layer 3)

**Built in:** Weeks 7–8, 11, 13

The engine of the product. Remove it and WattWise AI does not function.

## Components
| Module | Technique | Target | Measured |
|---|---|---|---|
| `forecasting.py` | Chronos (zero-shot) | MAPE ≤ 8% | ✅ ~2.0% |
| `darts_ensemble.py` | Backtested Darts XGBoost (seasonal lags) vs. Chronos, selects the winner | MAPE ≤ 8% | ✅ ~0.9% (XGBoost wins on this data) |
| `anomaly.py` | PyOD ensemble (IF + COPOD + ECOD), weighted score combination | F1 ≥ 0.88 | ✅ 0.927 |
| `lstm_autoencoder.py` | LSTM Autoencoder reconstruction error (Stage 2 confirmation) | ROC-AUC ≥ 0.90 | ✅ 0.917 |
| `drift_monitor.py` | Evidently AI / KS-test fallback (Stage 3 confirmation) | — | tested |
| `peak_optimizer.py` | XGBoost load-ranking regressor (explainable shed sequence) | — | tested |
| `optimization_clustering.py` | k-means on daily load shapes + per-cluster load-factor baseline | — | validated (see `docs/MODEL_EVIDENCE.md`) |
| `narrative.py` | Gemini 2.5 Flash + HF Inference API fallback + template fallback | — | tested |
| `cost_engine.py` | ToU rate engine (3rd energy domain) | — | tested |
| `notebooks/` | Colab training notebooks (T4 GPU) — export artefacts to Azure Blob | — | not started |

Real numbers, not targets restated as claims — see `docs/MODEL_EVIDENCE.md` for
methodology and known limitations (seed/facility variance) behind each ✅.

## Training vs inference
Training runs on **Google Colab free tier**. Inference runs on the **Azure B1s VM** via the FastAPI service in [`../api/`](../api/). MLflow tracks every experiment.

## The 3 mandated AI scenarios
peak demand · anomalous consumption · optimization opportunity — each covered by real ML (see `PROJECT_BLUEPRINT.md` §7).
