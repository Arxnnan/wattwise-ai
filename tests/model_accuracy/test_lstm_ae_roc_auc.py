"""Model accuracy gate — RFP §12: LSTM-AE ROC-AUC >= 0.90 on a labeled test set.

Also guards against regressing the index-alignment bug this project shipped
with: `reconstruction_error()` used to label each window's error with the
timestamp one step *after* the window (`series.index[seq_len:]`), so the
score was checked against the wrong point and ROC-AUC measured ~0.51 (random)
regardless of model quality. Fixed to `series.index[seq_len - 1 : -1]`.
"""
from __future__ import annotations
from sklearn.metrics import roc_auc_score

from ml.data_generator import generate_historical, get_facility_demand_series
from ml.lstm_autoencoder import LSTMAutoencoder

ROC_AUC_TARGET = 0.90


def _labeled_office_demand(seed: int = 42):
    df = generate_historical(days=60, interval_minutes=15, anomaly_rate=0.03, seed=seed)
    series = get_facility_demand_series(df, "office")
    labels = (
        df[(df.facility_id == "office") & (df.device_class == "main_meter") & (df.domain == "demand")]
        .set_index("ts")["is_anomaly"]
        .sort_index()
    )
    return series, labels


class TestLstmAeRocAucGate:

    def test_roc_auc_meets_rfp_target(self):
        series, labels = _labeled_office_demand()
        ae = LSTMAutoencoder()
        ae.fit(series)

        errors = ae.reconstruction_error(series)
        y_true = labels.reindex(errors.index, fill_value=False).astype(int).values

        auc = roc_auc_score(y_true, errors.values)
        assert auc >= ROC_AUC_TARGET, (
            f"LSTM-AE ROC-AUC {auc:.3f} is below the RFP target of {ROC_AUC_TARGET}"
        )

    def test_alignment_is_not_a_full_window_offset(self):
        # Regression guard for the specific bug: error index i should fall
        # INSIDE sequence i's span (series[i : i+seq_len]), not one step past
        # its end.
        series, _ = _labeled_office_demand()
        ae = LSTMAutoencoder(epochs=2)
        ae.fit(series)
        errors = ae.reconstruction_error(series)
        first_error_pos = series.index.get_loc(errors.index[0])
        assert first_error_pos == ae.seq_len - 1
