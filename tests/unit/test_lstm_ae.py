"""Unit tests — LSTM Autoencoder (anomaly Stage 2)."""
import pytest
import pandas as pd
import numpy as np


class TestLSTMAutoencoder:

    def test_fit_and_predict_returns_series(self, office_demand):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(epochs=1, seq_len=12)
        ae.fit(office_demand)
        confirmed = ae.predict(office_demand)
        assert isinstance(confirmed, pd.Series)

    def test_predict_length_less_than_input(self, office_demand):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(epochs=1, seq_len=12)
        ae.fit(office_demand)
        confirmed = ae.predict(office_demand)
        assert len(confirmed) <= len(office_demand)

    def test_confirms_spike_anomaly(self, office_demand):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(epochs=1, seq_len=12)
        ae.fit(office_demand)
        # Inject clear spike
        spiked = office_demand.copy()
        mid = len(spiked) // 2
        spiked.iloc[mid:mid+5] = spiked.mean() * 8.0
        confirmed = ae.predict(spiked)
        assert confirmed.any(), "LSTM-AE should detect 8x spike"

    def test_reconstruction_error_is_numeric(self, office_demand):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(epochs=1, seq_len=12)
        ae.fit(office_demand)
        errors = ae.reconstruction_error(office_demand)
        assert isinstance(errors, pd.Series)
        assert not errors.isna().any()
        assert (errors >= 0).all()

    def test_requires_fit(self, office_demand):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder()
        with pytest.raises(AssertionError):
            ae.predict(office_demand)
