"""Model accuracy gate — RFP §12: Anomaly F1 >= 0.88 on a labeled test set.

Uses the ground-truth `is_anomaly` column that `ml.data_generator` already
injects, so a real F1 (not a shape/smoke check) is computed and enforced.
Separate from tests/unit/ — this is its own QA category per the blueprint
(tool: scikit-learn harness), and it can regress independently of whether the
code still runs.
"""
from __future__ import annotations
from sklearn.metrics import f1_score

from ml.data_generator import generate_historical, get_facility_demand_series
from ml.anomaly import AnomalyDetector, _build_features

F1_TARGET = 0.88


def _labeled_office_demand(seed: int = 42):
    df = generate_historical(days=60, interval_minutes=15, anomaly_rate=0.03, seed=seed)
    series = get_facility_demand_series(df, "office")
    labels = (
        df[(df.facility_id == "office") & (df.device_class == "main_meter") & (df.domain == "demand")]
        .set_index("ts")["is_anomaly"]
        .sort_index()
    )
    return series, labels


class TestAnomalyF1Gate:

    def test_f1_meets_rfp_target(self):
        series, labels = _labeled_office_demand()
        detector = AnomalyDetector()
        detector.fit(series)

        features = _build_features(series)
        y_true = labels.reindex(features.index, fill_value=False).astype(int).values
        y_pred = detector.predict(series).reindex(features.index).astype(int).values

        f1 = f1_score(y_true, y_pred)
        assert f1 >= F1_TARGET, (
            f"Anomaly F1 {f1:.3f} is below the RFP target of {F1_TARGET}"
        )

    def test_positive_labels_exist(self):
        # Sanity check on the fixture itself — a passing F1 test is meaningless
        # if the generator injected zero anomalies for this seed.
        _, labels = _labeled_office_demand()
        assert labels.sum() > 50, "Too few injected anomalies to measure F1 reliably"
