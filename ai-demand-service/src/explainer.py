import numpy as np

from prediction import FEATURE_COLS


class OrderExplainer:
    def __init__(self, predictor):
        self.predictor = predictor
        self._shap = None

    def _ensure_explainer(self):
        if self._shap is None:
            import shap
            self._shap = shap.TreeExplainer(self.predictor.model)

    def explain(self, customer_id: int, product_id: int) -> dict | None:
        if not self.predictor.is_loaded():
            return None

        features = self.predictor.features
        row = features[
            (features["customer_id"] == customer_id)
            & (features["product_id"] == product_id)
        ]
        if row.empty:
            return None

        feature_row = row[FEATURE_COLS]

        self._ensure_explainer()
        shap_output = self._shap.shap_values(feature_row)

        values, base_value = _extract_class1(shap_output, self._shap.expected_value)

        feature_values = {col: float(feature_row.iloc[0][col]) for col in FEATURE_COLS}
        shap_by_feature = {col: float(v) for col, v in zip(FEATURE_COLS, values)}

        sorted_contribs = sorted(shap_by_feature.items(), key=lambda kv: kv[1], reverse=True)
        top_positive = [
            {"feature": f, "shap": round(v, 4), "value": round(feature_values[f], 4)}
            for f, v in sorted_contribs if v > 0
        ][:3]
        top_negative = [
            {"feature": f, "shap": round(v, 4), "value": round(feature_values[f], 4)}
            for f, v in reversed(sorted_contribs) if v < 0
        ][:3]

        prob = float(self.predictor.model.predict_proba(feature_row)[0][1])

        return {
            "customer_id": int(customer_id),
            "product_id": int(product_id),
            "reorder_probability": round(prob, 4),
            "base_value": round(float(base_value), 4),
            "feature_values": {k: round(v, 4) for k, v in feature_values.items()},
            "shap_values": {k: round(v, 4) for k, v in shap_by_feature.items()},
            "top_positive": top_positive,
            "top_negative": top_negative,
        }


def _extract_class1(shap_output, expected_value):
    """Normalise SHAP output across versions for binary classification.

    Returns (values_for_class_1, base_value_for_class_1).
    """
    arr = np.asarray(shap_output) if not isinstance(shap_output, list) else None

    if isinstance(shap_output, list):
        values = shap_output[1][0]
        base = expected_value[1] if hasattr(expected_value, "__len__") else expected_value
    elif arr is not None and arr.ndim == 3:
        values = arr[0, :, 1]
        base = expected_value[1] if hasattr(expected_value, "__len__") else expected_value
    else:
        values = arr[0]
        base = expected_value if np.isscalar(expected_value) else expected_value[0]

    return values, base
