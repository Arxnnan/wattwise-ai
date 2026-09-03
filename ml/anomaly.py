"""WattWise AI — anomaly detection (Stage 1: PyOD ensemble).

Uses a 3-algorithm weighted score ensemble:
  - IsolationForest (fast, tree-based)
  - COPOD (copula-based, parameter-free)
  - ECOD (empirical CDF-based, fast)

Each model's decision_function is percentile-rank-normalized (so IForest's
depth-based scores, COPOD's/ECOD's log-likelihood-based scores are on a
comparable 0-1 scale), then combined with weights tuned via Optuna against a
labeled validation set (see docs/MODEL_EVIDENCE.md) — an unweighted 2-of-3
vote left F1 around 0.54-0.85 because it let ECOD's weaker individual
performance veto correct calls from IForest+COPOD. The combined score is
thresholded at the contamination-implied percentile.
"""
from __future__ import annotations
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from pyod.models.iforest import IForest
from pyod.models.copod import COPOD
from pyod.models.ecod import ECOD
import mlflow

log = logging.getLogger(__name__)


def _build_features(series: pd.Series, window: int = 15) -> pd.DataFrame:
    """Engineer features from a demand time series.

    Uses a centered rolling median/MAD (not mean/std) as the local baseline:
    mean/std over a window that contains the anomaly itself get dragged toward
    the anomaly, which mutes the very deviation we're trying to detect. Median
    and MAD are robust to that contamination.
    """
    df = pd.DataFrame({"value": series})
    baseline = df["value"].rolling(window, center=True, min_periods=window // 2).median()
    mad = (df["value"] - baseline).abs().rolling(
        window, center=True, min_periods=window // 2
    ).median()
    df["robust_z"] = (df["value"] - baseline) / (1.4826 * mad + 1e-6)
    df["ratio"] = df["value"] / (baseline + 1e-6)
    df = df.dropna()
    return df


class AnomalyDetector:
    """PyOD 3-algorithm ensemble anomaly detector."""

    # Optuna-tuned against a labeled validation set (docs/MODEL_EVIDENCE.md).
    # IForest and COPOD carry most of the weight; ECOD contributes only as a
    # minor tie-breaker after tuning showed it individually underperforms on
    # this feature space (F1 ~0.53 alone vs COPOD's ~0.86-0.93 alone).
    _WEIGHTS = {"iforest": 0.45, "copod": 0.48, "ecod": 0.07}

    def __init__(self, contamination: float = 0.028):
        self.contamination = contamination
        self._models = {
            "iforest": IForest(contamination=contamination, random_state=42, n_jobs=1),
            "copod": COPOD(contamination=contamination),
            "ecod": ECOD(contamination=contamination),
        }
        self._fitted = False

    def fit(self, series: pd.Series, experiment_name: str = "wattwise-anomaly") -> dict:
        """Fit all 3 models. Returns training metrics."""
        features = _build_features(series)
        X = features[["robust_z", "ratio"]].values

        with mlflow.start_run(run_name="pyod-ensemble-fit"):
            mlflow.log_param("contamination", self.contamination)
            mlflow.log_param("n_samples", len(X))
            mlflow.log_param("models", list(self._models.keys()))
            mlflow.log_params({f"weight_{k}": v for k, v in self._WEIGHTS.items()})

            for name, model in self._models.items():
                model.fit(X)
                log.info("Fitted %s on %d samples", name, len(X))

            self._fitted = True
            n_anomalies = self.predict(series).sum()
            anomaly_rate = n_anomalies / len(series)
            mlflow.log_metric("detected_anomaly_rate", anomaly_rate)
            log.info("Ensemble fitted. Anomaly rate: %.3f", anomaly_rate)

        return {"n_samples": len(X), "anomaly_rate": anomaly_rate}

    def _combined_score(self, X: np.ndarray) -> np.ndarray:
        """Weighted, percentile-rank-normalized combination of the 3 models'
        decision functions — puts IForest's depth scores and COPOD's/ECOD's
        log-likelihood scores on the same comparable scale before combining."""
        combined = np.zeros(len(X))
        for name, model in self._models.items():
            ranks = pd.Series(model.decision_function(X)).rank(pct=True).values
            combined += self._WEIGHTS[name] * ranks
        return combined

    def predict(self, series: pd.Series) -> pd.Series:
        """Return boolean anomaly flags (True = anomaly)."""
        assert self._fitted, "Call fit() first"
        features = _build_features(series)
        X = features[["robust_z", "ratio"]].values

        combined = self._combined_score(X)
        threshold = np.percentile(combined, 100 * (1 - self.contamination))
        anomaly_flags = pd.Series(combined >= threshold, index=features.index, name="is_anomaly")
        return anomaly_flags

    def score(self, series: pd.Series) -> pd.Series:
        """Return raw anomaly scores (higher = more anomalous)."""
        assert self._fitted, "Call fit() first"
        features = _build_features(series)
        X = features[["robust_z", "ratio"]].values
        return pd.Series(self._combined_score(X), index=features.index, name="anomaly_score")

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        log.info("Model saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "AnomalyDetector":
        with open(path, "rb") as f:
            return pickle.load(f)
