"""WattWise AI — Optimization Opportunity scenario (blueprint §7.4, 3rd of the
3 mandated AI scenarios): k-means on hourly load shapes + per-cluster
efficiency baselines + narrative rationale.

Method:
  1. Build one 24-value "load shape" vector per (facility, calendar day) —
     mean demand (kW) for each hour of that day.
  2. Min-max normalize each shape to [0, 1] before clustering, so k-means
     groups days by *shape* (when the peak happens, how flat the profile is)
     rather than by facility size — a 120kW datacentre and a 45kW office
     should be able to land in the same cluster if their daily rhythm is
     similar, and clustering on raw kW would prevent that.
  3. Each cluster's efficiency baseline is its mean **load factor**
     (avg_kw / peak_kw for the day — a standard energy-engineering metric:
     closer to 1.0 means flatter, better utilized capacity; a low load
     factor means a sharp, expensive peak relative to how little energy
     surrounds it).
  4. A facility's "optimization opportunity" is the gap between its current
     load factor and the best cluster's, translated into a peak-kW (and
     therefore demand-charge) reduction estimate using the same
     `demand_charge_per_kw` rate `ml.cost_engine` already uses — reusing the
     existing rate rather than inventing a second, inconsistent one.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from ml.cost_engine import RATE_CONFIG

log = logging.getLogger(__name__)

N_HOURS = 24


@dataclass
class ClusterOpportunity:
    facility_id: str
    dominant_cluster: int
    facility_load_factor: float
    best_cluster_load_factor: float
    load_factor_gap: float
    avg_peak_kw: float
    estimated_peak_reduction_kw: float
    estimated_monthly_demand_charge_savings_inr: float


def build_daily_load_shapes(df: pd.DataFrame, device_class: str = "main_meter") -> pd.DataFrame:
    """Pivot telemetry demand rows into one row per (facility, date), columns
    hour_00..hour_23 = mean kW that hour. Also returns peak_kw/avg_kw/load_factor."""
    demand = df[(df["domain"] == "demand") & (df["device_class"] == device_class)].copy()
    demand["date"] = pd.to_datetime(demand["ts"]).dt.date
    demand["hour"] = pd.to_datetime(demand["ts"]).dt.hour

    pivot = demand.pivot_table(
        index=["facility_id", "date"], columns="hour", values="value", aggfunc="mean",
    )
    pivot = pivot.reindex(columns=range(N_HOURS))
    pivot.columns = [f"hour_{h:02d}" for h in range(N_HOURS)]
    pivot = pivot.dropna(how="any")  # keep only complete 24h days

    pivot["avg_kw"] = pivot.mean(axis=1)
    pivot["peak_kw"] = pivot[[c for c in pivot.columns if c.startswith("hour_")]].max(axis=1)
    pivot["load_factor"] = pivot["avg_kw"] / pivot["peak_kw"].replace(0, np.nan)
    return pivot.reset_index()


class LoadShapeClusterer:
    """K-means clustering of daily load shapes, with per-cluster efficiency
    baselines and a per-facility optimization-opportunity report."""

    def __init__(self, n_clusters: int = 4, random_state: int = 42):
        self.n_clusters = n_clusters
        self.random_state = random_state
        self._model: KMeans | None = None
        self._cluster_load_factors: dict[int, float] = {}
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> dict:
        shapes = build_daily_load_shapes(df)
        if len(shapes) < self.n_clusters:
            raise ValueError(
                f"Need at least {self.n_clusters} complete facility-days to fit "
                f"{self.n_clusters} clusters, got {len(shapes)}"
            )
        hour_cols = [c for c in shapes.columns if c.startswith("hour_")]
        X = shapes[hour_cols].values
        # Min-max normalize each day's own shape to [0, 1] — clusters group by
        # shape, not by facility size.
        row_min = X.min(axis=1, keepdims=True)
        row_max = X.max(axis=1, keepdims=True)
        X_norm = (X - row_min) / (row_max - row_min + 1e-9)

        self._model = KMeans(n_clusters=self.n_clusters, random_state=self.random_state, n_init=10)
        labels = self._model.fit_predict(X_norm)
        shapes["cluster"] = labels

        self._cluster_load_factors = shapes.groupby("cluster")["load_factor"].mean().to_dict()
        self._fitted = True
        log.info("Fitted %d clusters on %d facility-days. Load factors: %s",
                  self.n_clusters, len(shapes), {k: round(v, 3) for k, v in self._cluster_load_factors.items()})
        return {"n_facility_days": len(shapes), "cluster_load_factors": self._cluster_load_factors}

    def label_days(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return the daily-shape table with a `cluster` column assigned."""
        assert self._fitted, "Call fit() first"
        shapes = build_daily_load_shapes(df)
        hour_cols = [c for c in shapes.columns if c.startswith("hour_")]
        X = shapes[hour_cols].values
        row_min = X.min(axis=1, keepdims=True)
        row_max = X.max(axis=1, keepdims=True)
        X_norm = (X - row_min) / (row_max - row_min + 1e-9)
        shapes["cluster"] = self._model.predict(X_norm)
        return shapes

    def opportunity_report(self, df: pd.DataFrame) -> list[ClusterOpportunity]:
        """Per-facility optimization opportunity vs. the most-efficient cluster."""
        assert self._fitted, "Call fit() first"
        labeled = self.label_days(df)
        best_cluster_lf = max(self._cluster_load_factors.values())

        report = []
        for facility_id, group in labeled.groupby("facility_id"):
            dominant_cluster = int(group["cluster"].mode().iloc[0])
            facility_lf = float(group["load_factor"].mean())
            avg_peak_kw = float(group["peak_kw"].mean())
            gap = max(0.0, best_cluster_lf - facility_lf)

            # Same total energy, higher load factor -> lower peak: peak = avg / load_factor
            target_lf = min(best_cluster_lf, 0.999)
            target_peak_kw = group["avg_kw"].mean() / target_lf if target_lf > 0 else avg_peak_kw
            peak_reduction_kw = max(0.0, avg_peak_kw - target_peak_kw)
            monthly_savings_inr = peak_reduction_kw * RATE_CONFIG.demand_charge_per_kw

            report.append(ClusterOpportunity(
                facility_id=facility_id,
                dominant_cluster=dominant_cluster,
                facility_load_factor=round(facility_lf, 4),
                best_cluster_load_factor=round(best_cluster_lf, 4),
                load_factor_gap=round(gap, 4),
                avg_peak_kw=round(avg_peak_kw, 2),
                estimated_peak_reduction_kw=round(peak_reduction_kw, 2),
                estimated_monthly_demand_charge_savings_inr=round(monthly_savings_inr, 2),
            ))
        return sorted(report, key=lambda r: r.estimated_monthly_demand_charge_savings_inr, reverse=True)


def build_optimization_narrative_context(opp: ClusterOpportunity) -> str:
    """Text suitable for `ml.narrative.NarrativeRequest(narrative_type='optimization', extra_context=...)`."""
    return (
        f"Load-shape clustering (k-means, cluster {opp.dominant_cluster}) shows this facility's "
        f"typical daily load factor is {opp.facility_load_factor:.2f} versus {opp.best_cluster_load_factor:.2f} "
        f"for the most efficient observed pattern. Flattening the daily profile toward that pattern "
        f"could reduce peak demand by roughly {opp.estimated_peak_reduction_kw:.1f} kW, worth about "
        f"Rs.{opp.estimated_monthly_demand_charge_savings_inr:.0f}/month in demand charges at "
        f"Rs.{RATE_CONFIG.demand_charge_per_kw:.0f}/kW."
    )
