"""WattWise AI — XGBoost load-ranking optimizer (Peak Demand Management).

When Chronos+Darts forecast predicts demand > 90% of threshold,
this optimizer scores all controllable loads and emits a ranked
shed sequence: which loads to defer, in what order, to avoid the peak.

Scoring function:
  f(deferrability_class, demand_contribution_kW, comfort_impact, response_time_min)

Model: XGBoost regressor trained on labeled historical shed events.
Falls back to rule-based ranking if model not yet trained.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

DeferClass = Literal["high", "medium", "low"]  # high = easy to defer


@dataclass
class ControllableLoad:
    """A load that can be shed during peak events."""
    load_id: str
    device_class: str
    facility_id: str
    current_kw: float
    deferrability_class: DeferClass   # high / medium / low
    comfort_impact: float             # 0.0 (no impact) to 1.0 (high impact)
    response_time_minutes: float      # how quickly it can respond


@dataclass
class ShedRecommendation:
    """Output: ranked list of loads to shed."""
    load_id: str
    device_class: str
    current_kw: float
    shed_score: float     # higher = shed this first
    rank: int
    action: str
    estimated_kw_saved: float


class PeakOptimizer:
    """XGBoost load-ranking optimizer with rule-based fallback."""

    def __init__(self, peak_threshold_kw: float = 300.0,
                 warn_ratio: float = 0.90):
        self.peak_threshold_kw = peak_threshold_kw
        self.warn_ratio = warn_ratio
        self._model = None
        self._fitted = False

    def fit(self, training_events: pd.DataFrame) -> dict:
        """Train XGBoost on historical shed events.

        training_events columns:
          deferrability_class (encoded), demand_contribution_kw,
          comfort_impact, response_time_min, was_shed_first (target)
        """
        try:
            import xgboost as xgb
            from sklearn.preprocessing import LabelEncoder

            df = training_events.copy()
            le = LabelEncoder()
            df["defer_encoded"] = le.fit_transform(df["deferrability_class"])
            self._label_encoder = le

            features = ["defer_encoded", "demand_contribution_kw",
                        "comfort_impact", "response_time_min"]
            X = df[features].values
            y = df["was_shed_first"].values

            self._model = xgb.XGBClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                use_label_encoder=False, eval_metric="logloss", random_state=42
            )
            self._model.fit(X, y)
            self._fitted = True
            log.info("XGBoost load-ranker fitted on %d events", len(df))
            return {"n_training_events": len(df), "method": "xgboost"}
        except Exception as e:
            log.warning("XGBoost training failed (%s) — using rule-based fallback", e)
            self._fitted = True
            return {"method": "rule_based_fallback"}

    def rank_loads(self, loads: list[ControllableLoad],
                   current_demand_kw: float,
                   target_reduction_kw: float) -> list[ShedRecommendation]:
        """Rank loads by shed priority. Returns ordered shed plan."""
        if not loads:
            return []

        if self._model is not None:
            return self._ml_rank(loads, current_demand_kw, target_reduction_kw)
        return self._rule_rank(loads, current_demand_kw, target_reduction_kw)

    def _ml_rank(self, loads, current_demand_kw, target_reduction_kw):
        defer_map = {"high": 0, "medium": 1, "low": 2}
        rows = []
        for load in loads:
            rows.append([
                defer_map.get(load.deferrability_class, 1),
                load.current_kw,
                load.comfort_impact,
                load.response_time_minutes,
            ])
        X = np.array(rows)
        scores = self._model.predict_proba(X)[:, 1]
        return self._build_recommendations(loads, scores, target_reduction_kw)

    def _rule_rank(self, loads, current_demand_kw, target_reduction_kw):
        defer_weight = {"high": 1.0, "medium": 0.5, "low": 0.1}
        scores = []
        for load in loads:
            score = (
                defer_weight.get(load.deferrability_class, 0.5) * 0.5
                + (load.current_kw / (current_demand_kw + 1e-6)) * 0.3
                + (1 - load.comfort_impact) * 0.15
                + (1 / (load.response_time_minutes + 1)) * 0.05
            )
            scores.append(score)
        return self._build_recommendations(loads, scores, target_reduction_kw)

    def _build_recommendations(self, loads, scores, target_reduction_kw):
        ranked = sorted(zip(loads, scores), key=lambda x: x[1], reverse=True)
        recommendations = []
        cumulative_saved = 0.0
        for rank, (load, score) in enumerate(ranked, start=1):
            action = "DEFER" if load.deferrability_class == "high" else "REDUCE"
            recommendations.append(ShedRecommendation(
                load_id=load.load_id,
                device_class=load.device_class,
                current_kw=load.current_kw,
                shed_score=round(float(score), 4),
                rank=rank,
                action=action,
                estimated_kw_saved=load.current_kw if action == "DEFER" else load.current_kw * 0.5,
            ))
            cumulative_saved += load.current_kw
            if cumulative_saved >= target_reduction_kw:
                break
        return recommendations

    def should_activate(self, predicted_kw: float) -> bool:
        """Return True if peak warning threshold is crossed."""
        return predicted_kw >= self.peak_threshold_kw * self.warn_ratio

    def generate_synthetic_training_data(self, n_events: int = 500,
                                         seed: int = 42) -> pd.DataFrame:
        """Generate synthetic shed events for bootstrapping the XGBoost model."""
        rng = np.random.default_rng(seed)
        defer_classes = rng.choice(["high", "medium", "low"], size=n_events,
                                   p=[0.4, 0.4, 0.2])
        demand = rng.uniform(5, 100, n_events)
        comfort = rng.uniform(0, 1, n_events)
        response = rng.uniform(1, 30, n_events)

        # Ground truth: high deferrability + high demand + low comfort → shed first
        defer_score = np.where(defer_classes == "high", 1.0,
                               np.where(defer_classes == "medium", 0.5, 0.1))
        shed_prob = 0.5 * defer_score + 0.3 * (demand / 100) + 0.2 * (1 - comfort)
        was_shed_first = (rng.uniform(0, 1, n_events) < shed_prob).astype(int)

        return pd.DataFrame({
            "deferrability_class": defer_classes,
            "demand_contribution_kw": demand,
            "comfort_impact": comfort,
            "response_time_min": response,
            "was_shed_first": was_shed_first,
        })
