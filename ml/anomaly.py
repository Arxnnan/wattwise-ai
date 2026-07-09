"""WattWise AI — anomaly detection (Stage 1: PyOD ensemble).

Uses a 3-algorithm voting ensemble:
  - IsolationForest (fast, tree-based)
  - COPOD (copula-based, parameter-free)
  - ECOD (empirical CDF-based, fast)

Any 2-of-3 vote = anomaly flagged.
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


def _build_features(series: pd.Series, window: int = 12) -> pd.DataFrame:
    """Engineer features from a demand time series."""
    df = pd.DataFrame({"value": series})
    df["rolling_mean"] = df["value"].rolling(window).mean()
    df["rolling_std"] = df["value"].rolling(window).std()
    df["z_score"] = (df["value"] - df["rolling_mean"]) / (df["rolling_std"] + 1e-6)
    df["pct_change"] = df["value"].pct_change()
    df["hour"] = df.index.hour if hasattr(df.index, "hour") else 0
    df = df.dropna()
    return df


class AnomalyDetector:
    """PyOD 3-algorithm ensemble anomaly detector."""

    def __init__(self, contamination: float = 0.02):
        self.contamination = contamination
        self._models = {
            "iforest": IForest(contamination=contamination, random_state=42, n_jobs=-1),
            "copod": COPOD(contamination=contamination),
            "ecod": ECOD(contamination=contamination),
        }
        self._fitted = False

    def fit(self, series: pd.Series, experiment_name: str = "wattwise-anomaly") -> dict:
        """Fit all 3 models. Returns training metrics."""
        features = _build_features(series)
        X = features[["value", "rolling_mean", "rolling_std", "z_score", "pct_change"]].values

        with mlflow.start_run(run_name="pyod-ensemble-fit"):
            mlflow.log_param("contamination", self.contamination)
            mlflow.log_param("n_samples", len(X))
            mlflow.log_param("models", list(self._models.keys()))

            for name, model in self._models.items():
                model.fit(X)
                log.info("Fitted %s on %d samples", name, len(X))

            self._fitted = True
            n_anomalies = self.predict(series).sum()
            anomaly_rate = n_anomalies / len(series)
            mlflow.log_metric("detected_anomaly_rate", anomaly_rate)
            log.info("Ensemble fitted. Anomaly rate: %.3f", anomaly_rate)

        return {"n_samples": len(X), "anomaly_rate": anomaly_rate}

    def predict(self, series: pd.Series) -> pd.Series:
        """Return boolean anomaly flags (True = anomaly)."""
        assert self._fitted, "Call fit() first"
        features = _build_features(series)
        X = features[["value", "rolling_mean", "rolling_std", "z_score", "pct_change"]].values

        votes = np.zeros(len(X), dtype=int)
        for name, model in self._models.items():
            preds = model.predict(X)  # 0=normal, 1=anomaly
            votes += preds

        # 2-of-3 majority vote
        anomaly_flags = pd.Series(votes >= 2, index=features.index, name="is_anomaly")
        return anomaly_flags

    def score(self, series: pd.Series) -> pd.Series:
        """Return raw anomaly scores (higher = more anomalous)."""
        assert self._fitted, "Call fit() first"
        features = _build_features(series)
        X = features[["value", "rolling_mean", "rolling_std", "z_score", "pct_change"]].values

        scores = np.zeros(len(X))
        for model in self._models.values():
            scores += model.decision_function(X)
        return pd.Series(scores / len(self._models), index=features.index, name="anomaly_score")

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
