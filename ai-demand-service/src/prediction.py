import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "models" / "order_prediction_model.pkl"
METADATA_PATH = BASE_DIR / "models" / "model_metadata.json"
CSV_PATH = BASE_DIR / "data" / "Order_history.csv"

FEATURE_COLS = [
    "order_count",
    "days_since_last_order",
    "avg_quantity",
    "order_gap_std",
    "total_spend",
    "customer_total_orders",
    "product_popularity",
]


def _order_gap_std(dates):
    if len(dates) < 2:
        return np.nan
    sorted_dates = sorted(dates)
    gaps = [(sorted_dates[i + 1] - sorted_dates[i]).days for i in range(len(sorted_dates) - 1)]
    return float(np.std(gaps))


def build_features(df: pd.DataFrame, reference_date) -> pd.DataFrame:
    """Reproduces the feature engineering used in the training notebook."""
    order_counts = (
        df.groupby(["customer_id", "product_id"]).size().reset_index(name="order_count")
    )

    last_order = (
        df.groupby(["customer_id", "product_id"])["order_date"].max().reset_index()
    )
    last_order["days_since_last_order"] = (reference_date - last_order["order_date"]).dt.days
    last_order = last_order.drop(columns="order_date")

    avg_qty = (
        df.groupby(["customer_id", "product_id"])["quantity"]
        .mean().reset_index(name="avg_quantity")
    )

    regularity = (
        df.groupby(["customer_id", "product_id"])["order_date"]
        .apply(_order_gap_std).reset_index(name="order_gap_std")
    )

    total_spend = (
        df.assign(spend=df["quantity"] * df["price"])
        .groupby(["customer_id", "product_id"])["spend"]
        .sum().reset_index(name="total_spend")
    )

    customer_order_count = (
        df.groupby("customer_id")["order_id"]
        .nunique().reset_index(name="customer_total_orders")
    )

    product_popularity = (
        df.groupby("product_id")["order_id"]
        .nunique().reset_index(name="product_popularity")
    )

    features = (
        order_counts
        .merge(last_order, on=["customer_id", "product_id"])
        .merge(avg_qty, on=["customer_id", "product_id"])
        .merge(regularity, on=["customer_id", "product_id"])
        .merge(total_spend, on=["customer_id", "product_id"])
        .merge(customer_order_count, on="customer_id")
        .merge(product_popularity, on="product_id")
    )

    features["order_gap_std"] = features["order_gap_std"].fillna(
        features["order_gap_std"].max()
    )
    return features



class OrderPredictor:
    def __init__(self):
        self.model = None
        self.metadata = {}
        self.features = None
        self.product_names = {}

    def load(self):
        if not MODEL_PATH.exists() or not CSV_PATH.exists():
            print(f"Model or CSV missing (model={MODEL_PATH.exists()}, csv={CSV_PATH.exists()})")
            return False

        self.model = joblib.load(MODEL_PATH)
        if METADATA_PATH.exists():
            self.metadata = json.loads(METADATA_PATH.read_text())

        df = pd.read_csv(CSV_PATH)
        df["order_date"] = pd.to_datetime(df["order_date"], format="%d/%m/%Y")
        cutoff_date = df["order_date"].quantile(0.8)
        train_df = df[df["order_date"] <= cutoff_date].copy()
        self.features = build_features(train_df, cutoff_date)

        if "product_name" in df.columns:
            self.product_names = dict(df.drop_duplicates("product_id")[["product_id", "product_name"]].values)
        return True

    def is_loaded(self) -> bool:
        return self.model is not None and self.features is not None

    def recommend(self, customer_id: int, top_n: int = 5) -> list[dict]:
        cust_rows = self.features[self.features["customer_id"] == customer_id]
        if cust_rows.empty:
            return []

        probs = self.model.predict_proba(cust_rows[FEATURE_COLS])[:, 1]
        out = cust_rows[["product_id"]].copy()
        out["reorder_probability"] = probs
        out = out.sort_values("reorder_probability", ascending=False).head(top_n)

        return [
            {
                "product_id": int(row.product_id),
                "product_name": self.product_names.get(int(row.product_id)),
                "reorder_probability": round(float(row.reorder_probability), 4),
            }
            for row in out.itertuples()
        ]

    def known_customers(self) -> list[int]:
        if self.features is None:
            return []
        return sorted(self.features["customer_id"].unique().tolist())
    
    def forecast(self, days: int = 7) -> list[dict]:
        df = pd.read_csv(CSV_PATH)
        df["order_date"] = pd.to_datetime(df["order_date"], format="%d/%m/%Y")

        max_date = df["order_date"].max()

        # Last 4 weeks of data for recent trend
        recent = df[df["order_date"] >= max_date - pd.Timedelta(weeks=4)]
        # Previous 4 weeks for comparison
        previous = df[
            (df["order_date"] >= max_date - pd.Timedelta(weeks=8))
            & (df["order_date"] < max_date - pd.Timedelta(weeks=4))
        ]

        recent_demand = (
            recent.groupby("product_id")["quantity"]
            .sum()
            .reset_index(name="recent_qty")
        )
        previous_demand = (
            previous.groupby("product_id")["quantity"]
            .sum()
            .reset_index(name="previous_qty")
        )

        merged = recent_demand.merge(previous_demand, on="product_id", how="left")
        merged["previous_qty"] = merged["previous_qty"].fillna(0)

        # Calculate trend
        merged["trend"] = np.where(
            merged["previous_qty"] > 0,
            ((merged["recent_qty"] - merged["previous_qty"]) / merged["previous_qty"] * 100).round(1),
            100.0,
        )
        merged["trend"] = np.clip(merged["trend"], -100, 200)
        # Classify demand level
        median_qty = merged["recent_qty"].median()
        merged["level"] = np.where(
            merged["recent_qty"] >= median_qty * 1.3, "high",
            np.where(merged["recent_qty"] <= median_qty * 0.7, "low", "medium")
        )

        # Forecast next period quantity (simple: recent weekly avg * days/7)
        weeks_in_recent = 4
        merged["forecast_qty"] = (
            (merged["recent_qty"] / weeks_in_recent) * (days / 7)
        ).round(0).astype(int)

        # Build response
        forecasts = []
        for row in merged.sort_values("recent_qty", ascending=False).itertuples():
            product_name = self.product_names.get(int(row.product_id), f"Product {row.product_id}")
            
            if row.level == "high":
                description = f"High demand expected — consider increasing stock"
            elif row.level == "low":
                description = f"Low demand expected — reduce stock to avoid waste"
            else:
                description = f"Steady demand expected"

            forecasts.append({
                "product_id": int(row.product_id),
                "product_name": product_name,
                "level": row.level,
                "forecast_quantity": int(row.forecast_qty),
                "trend_percent": float(row.trend),
                "description": description,
            })

        return forecasts
