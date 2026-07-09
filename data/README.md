# data/ — Datasets

**Built in:** Week 4

Seed datasets used to train models on realistic energy patterns from day one. Raw/processed data is gitignored; only `seed/` references and small samples are tracked.

## seed/ datasets
| Dataset | Source | Use |
|---|---|---|
| UCI Individual Household Electric Power Consumption | UCI ML Repository | Base load shapes, forecasting train data |
| ASHRAE Great Energy Predictor III | Kaggle | Multi-building consumption patterns |
| OpenEI Commercial Reference Building Load Profiles | OpenEI / NREL | Facility-type-specific demand curves |

## Notes
- `data/raw/` and `data/processed/` are gitignored (large files).
- Download instructions and a `seed_loader.py` live in [`../ingestion/`](../ingestion/).
- These datasets feed the simulators so generated telemetry resembles real facilities.
