import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeRegressor

from database import (
    add_model_registry,
    deactivate_models,
    get_active_model_record,
    latest_metrics,
    list_model_registry,
    list_price_history,
    utc_now,
)


class ModelService:
    def __init__(self, config):
        self.config = config
        self.model_dir = Path(config["MODEL_DIR"])
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def train_and_register(self, symbol, target_model="both", uploaded_df=None, params=None, horizon_days=1):
        params = params or {}
        df = uploaded_df if uploaded_df is not None else self.load_asset_dataframe(symbol)
        frame = self.prepare_training_frame(df, horizon_days=horizon_days)
        X = frame[[f"lag_{idx}" for idx in range(1, 7)]]
        y = frame["target"]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        results = {}
        if target_model in {"dt", "both"}:
            dt_params = {
                "random_state": 42,
                "max_depth": params.get("dt_max_depth"),
                "min_samples_split": max(int(params.get("dt_min_samples", 2)), 2),
            }
            model = DecisionTreeRegressor(**dt_params)
            model.fit(X_train, y_train)
            metrics = self.evaluate_model(model, X_test, y_test)
            path = self._dump_model(symbol, "dt", model)
            deactivate_models(symbol, "dt", horizon_days)
            add_model_registry(
                self._registry_record(symbol, "dt", horizon_days, metrics, dt_params, model, path)
            )
            results["dt"] = {"metrics": metrics, "model_path": str(path)}

        if target_model in {"rf", "both"}:
            rf_params = {
                "random_state": 42,
                "n_estimators": max(int(params.get("rf_estimators", 100)), 10),
                "max_depth": params.get("rf_max_depth"),
            }
            model = RandomForestRegressor(**rf_params)
            model.fit(X_train, y_train)
            metrics = self.evaluate_model(model, X_test, y_test)
            path = self._dump_model(symbol, "rf", model)
            deactivate_models(symbol, "rf", horizon_days)
            add_model_registry(
                self._registry_record(symbol, "rf", horizon_days, metrics, rf_params, model, path)
            )
            results["rf"] = {"metrics": metrics, "model_path": str(path)}

        return results

    def predict(self, symbol, days=1):
        df = self.load_asset_dataframe(symbol)
        latest_features = self._latest_features(df)
        history = df["Close"].tail(6).to_numpy()

        dt_model = self.load_active_model(symbol, "dt", horizon_days=days)
        rf_model = self.load_active_model(symbol, "rf", horizon_days=days)
        if dt_model is None or rf_model is None:
            self.train_and_register(symbol, target_model="both", horizon_days=days)
            dt_model = self.load_active_model(symbol, "dt", horizon_days=days)
            rf_model = self.load_active_model(symbol, "rf", horizon_days=days)

        dt_prediction = float(dt_model.predict(latest_features)[0])
        rf_prediction = float(rf_model.predict(latest_features)[0])
        labels = list(df["Date"].tail(6).astype(str)) + [f"+{days} day(s)"]
        return {
            "labels_current": list(df["Date"].tail(6).astype(str)),
            "labels_prediction": labels,
            "history": history.tolist(),
            "dt_series": np.append(history, dt_prediction).tolist(),
            "rf_series": np.append(history, rf_prediction).tolist(),
            "current_price": float(history[-1]),
            "dt_prediction": dt_prediction,
            "rf_prediction": rf_prediction,
        }

    def get_latest_metrics(self, symbol):
        return latest_metrics(symbol)

    def get_model_registry(self, symbol=None, limit=10):
        return list_model_registry(symbol=symbol, limit=limit)

    def load_asset_dataframe(self, symbol):
        rows = list_price_history(symbol)
        if not rows:
            raise ValueError(f"No price history found for {symbol}")
        df = pd.DataFrame(rows)
        df.rename(
            columns={
                "trade_date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "adj_close": "Adj Close",
                "volume": "Volume",
            },
            inplace=True,
        )
        return df[["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]]

    def prepare_training_frame(self, df, horizon_days=1):
        frame = df[["Date", "Close"]].copy()
        for lag in range(1, 7):
            frame[f"lag_{lag}"] = frame["Close"].shift(lag)
        frame["target"] = frame["Close"].shift(-horizon_days)
        return frame.dropna().reset_index(drop=True)

    def evaluate_model(self, model, X_test, y_test):
        predictions = model.predict(X_test)
        return {
            "rmse": float(np.sqrt(mean_squared_error(y_test, predictions))),
            "mae": float(mean_absolute_error(y_test, predictions)),
            "r2": float(r2_score(y_test, predictions)),
        }

    def load_active_model(self, symbol, model_name, horizon_days=1):
        record = get_active_model_record(symbol, model_name, horizon_days)
        if record is None:
            return None
        path = Path(record["model_path"])
        if not path.exists():
            return None
        try:
            return joblib.load(path)
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _latest_features(self, df):
        latest = df[["Close"]].copy()
        for lag in range(1, 7):
            latest[f"lag_{lag}"] = latest["Close"].shift(lag)
        latest = latest.dropna().tail(1)
        return latest[[f"lag_{idx}" for idx in range(1, 7)]]

    def _dump_model(self, symbol, model_name, model):
        version = f"{symbol.lower()}_{model_name}_{utc_now().replace(':', '-').replace('+00:00', 'z')}"
        path = self.model_dir / f"{version}.joblib"
        joblib.dump(model, path)
        return path

    def _registry_record(self, symbol, model_name, horizon_days, metrics, params, model, path):
        feature_importances = getattr(model, "feature_importances_", None)
        return {
            "asset_symbol": symbol.upper(),
            "model_name": model_name,
            "version": Path(path).stem,
            "horizon_days": horizon_days,
            "trained_at": utc_now(),
            "rmse": metrics["rmse"],
            "mae": metrics["mae"],
            "r2": metrics["r2"],
            "params_json": json.dumps(params),
            "feature_importances_json": json.dumps(
                [round(float(item), 6) for item in feature_importances.tolist()]
            ) if feature_importances is not None else json.dumps([]),
            "model_path": str(path),
            "dataset_source": "price_history",
            "is_active": True,
        }
