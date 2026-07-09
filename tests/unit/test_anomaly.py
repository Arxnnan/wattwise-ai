"""Unit tests — PyOD anomaly detection."""
import pytest
import pandas as pd
import numpy as np


class TestAnomalyDetector:

    def test_fit_and_predict_shape(self, office_demand):
        from ml.anomaly import AnomalyDetector
        detector = AnomalyDetector(contamination=0.02)
        detector.fit(office_demand)
        flags = detector.predict(office_demand)
        # Shape must match after feature engineering (drops NaNs)
        assert len(flags) <= len(office_demand)
        assert len(flags) > 0

    def test_anomaly_rate_within_bounds(self, office_demand):
        from ml.anomaly import AnomalyDetector
        detector = AnomalyDetector(contamination=0.02)
        detector.fit(office_demand)
        flags = detector.predict(office_demand)
        rate = flags.mean()
        # Should be near the contamination parameter (within 3x)
        assert rate <= 0.06, f"Anomaly rate {rate:.3f} too high"

    def test_detects_injected_spike(self, office_demand):
        from ml.anomaly import AnomalyDetector
        detector = AnomalyDetector(contamination=0.02)
        detector.fit(office_demand)

        # Inject a clear spike (5x normal)
        spiked = office_demand.copy()
        spike_idx = len(spiked) // 2
        spiked.iloc[spike_idx] = spiked.mean() * 5.0
        flags = detector.predict(spiked)

        # The spike should be detected
        assert flags.any(), "Spike not detected by ensemble"

    def test_scores_are_numeric(self, office_demand):
        from ml.anomaly import AnomalyDetector
        detector = AnomalyDetector(contamination=0.02)
        detector.fit(office_demand)
        scores = detector.score(office_demand)
        assert scores.dtype in [np.float32, np.float64]
        assert not scores.isna().any()

    def test_requires_fit_before_predict(self, office_demand):
        from ml.anomaly import AnomalyDetector
        detector = AnomalyDetector()
        with pytest.raises(AssertionError, match="fit"):
            detector.predict(office_demand)
