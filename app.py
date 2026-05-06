from copy import deepcopy
from datetime import datetime, timedelta
from flask import Flask, Response, flash, jsonify, redirect, render_template, request, send_file, session, url_for
import json
import pickle
import os
import threading
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeRegressor
from werkzeug.utils import secure_filename

import TreePredict

app = Flask(__name__)
app.secret_key = "super_secret_key_hcmut"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
STATE_FILE = os.path.join(DATA_DIR, "app_state.json")
MAX_AUDIT_LOGS = 100
STATE_LOCK = threading.RLock()
REQUIRED_DATASET_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
FEATURE_LABELS = ["T-1 (Yesterday)", "T-2", "T-3", "T-4", "T-5", "T-6"]
ROLE_LABELS = {
    "admin": "System Admin",
    "scientist": "Data Scientist",
    "user": "End User",
}


def seed_state():
    return {
        "users": {
            "admin": {
                "password": "123",
                "role": "admin",
                "display_name": "Kien Nguyen",
                "email": "kien.nguyen@hcmut.edu.vn",
                "last_login": "Never",
            },
            "scientist": {
                "password": "123",
                "role": "scientist",
                "display_name": "Canh Phi",
                "email": "phi.canhvan@hcmut.edu.vn",
                "last_login": "Never",
            },
            "kien": {
                "password": "123",
                "role": "user",
                "display_name": "Thai Pham",
                "email": "thaipham@gmail.com",
                "last_login": "Never",
            },
        },
        "notifications": [
            {
                "id": 1,
                "type": "warning",
                "title": "System Alert",
                "message": "BTC model accuracy dropped below threshold. Retrain recommended.",
                "sender": "Automated Monitor",
                "created_at": "2026-04-24 09:00",
                "read": False,
            },
            {
                "id": 2,
                "type": "admin",
                "title": "Admin Message",
                "message": "Check the recent volatility in ETH dataset.",
                "sender": "admin",
                "created_at": "2026-04-24 08:00",
                "read": False,
            },
            {
                "id": 3,
                "type": "info",
                "title": "Pipeline",
                "message": "Weekly automated data backup completed successfully.",
                "sender": "System",
                "created_at": "2026-04-23 10:00",
                "read": True,
            },
        ],
        "audit_logs": [
            {
                "timestamp": "2026-04-24 09:10",
                "event": "User kien predicted BTC (30 days)",
                "status": "Success",
            },
            {
                "timestamp": "2026-04-24 08:40",
                "event": "Admin modified role for scientist",
                "status": "Success",
            },
            {
                "timestamp": "2026-04-24 07:55",
                "event": "Failed login attempt (username: unknown_user)",
                "status": "Warning",
            },
        ],
        "scientist_metrics": {
            "dt_rmse": "1,245.50",
            "dt_mae": "980.20",
            "dt_r2": "0.8920",
            "rf_rmse": "850.75",
            "rf_mae": "610.30",
            "rf_r2": "0.9850",
            "last_trained": "07/04/2026",
        },
        "feature_importance": {
            "labels": FEATURE_LABELS,
            "values": [65.2, 15.8, 8.4, 5.1, 3.5, 2.0],
        },
        "model_registry": [
            {
                "id": 1,
                "version": "v2.1.0",
                "trained_at": "2026-04-07 20:30",
                "model_name": "rf",
                "formatted_params": "Trees: 100 | Depth: Auto",
                "r2": 0.985,
                "artifact_name": "rf_v2.1.0.pkl",
            },
            {
                "id": 2,
                "version": "v2.0.5",
                "trained_at": "2026-03-25 14:15",
                "model_name": "dt",
                "formatted_params": "Min Split: 2 | Depth: 10",
                "r2": 0.892,
                "artifact_name": "dt_v2.0.5.pkl",
            },
        ],
        "request_metrics": {
            "total_requests": 0,
            "daily_counts": {},
        },
    }


def ensure_state_file():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        write_state(seed_state())


def read_state():
    ensure_state_file()
    with STATE_LOCK:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip()
        except FileNotFoundError:
            raw = ""

        if not raw:
            state = seed_state()
            write_state(state)
            return state

        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            backup_path = f"{STATE_FILE}.corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            try:
                with open(backup_path, "w", encoding="utf-8") as backup_file:
                    backup_file.write(raw)
            except OSError:
                pass
            state = seed_state()
            write_state(state)
            return state

    changed = False
    if "request_metrics" not in state:
        state["request_metrics"] = {
            "total_requests": 0,
            "daily_counts": {},
        }
        changed = True
    metrics = state.setdefault("scientist_metrics", {})
    metric_defaults = seed_state()["scientist_metrics"]
    for key, value in metric_defaults.items():
        if key not in metrics:
            metrics[key] = value
            changed = True
    if "feature_importance" not in state:
        state["feature_importance"] = seed_state()["feature_importance"]
        changed = True
    if "model_registry" not in state:
        state["model_registry"] = seed_state()["model_registry"]
        changed = True

    if changed:
        write_state(state)

    return state


def write_state(state):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    temp_path = f"{STATE_FILE}.tmp"
    with STATE_LOCK:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(temp_path, STATE_FILE)
        except PermissionError:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.remove(temp_path)
            except OSError:
                pass


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def role_label(role):
    return ROLE_LABELS.get(role, role.title())


def add_audit_log(state, event, status="Success"):
    logs = state.setdefault("audit_logs", [])
    logs.insert(
        0,
        {
            "timestamp": now_str(),
            "event": event,
            "status": status,
        },
    )
    del logs[MAX_AUDIT_LOGS:]


def next_notification_id(notifications):
    return max((item["id"] for item in notifications), default=0) + 1


def build_admin_users(users):
    rows = []
    for username, user in users.items():
        rows.append(
            {
                "username": username,
                "display_name": user.get("display_name", username),
                "email": user.get("email", ""),
                "role": user.get("role", "user"),
                "role_label": role_label(user.get("role", "user")),
                "last_login": user.get("last_login", "Never"),
                "protected": username == "admin",
            }
        )
    return sorted(rows, key=lambda item: item["username"])


def latest_admin_message(notifications):
    for item in notifications:
        if item.get("type") == "admin":
            return item
    return None


def current_scientist(state):
    username = session.get("username", "scientist")
    user = state.get("users", {}).get(username, {})
    return {
        "username": username,
        "full_name": user.get("display_name", username),
        "role": user.get("role", "scientist"),
    }


def format_optional_depth(value):
    return value if value not in (None, "", "-") else "Auto"


def format_model_params(form, model_name):
    if model_name == "rf":
        return (
            f"Trees: {form.get('rf_estimators', '100') or '100'} | "
            f"Depth: {format_optional_depth(form.get('rf_max_depth'))}"
        )
    return (
        f"Min Split: {form.get('dt_min_samples', '2') or '2'} | "
        f"Depth: {format_optional_depth(form.get('dt_max_depth'))}"
    )


def parse_optional_int(value, default=None):
    if value in (None, "", "-"):
        return default
    return int(value)


def parse_retrain_params(form):
    return {
        "dt_max_depth": parse_optional_int(form.get("dt_max_depth")),
        "dt_min_samples": max(parse_optional_int(form.get("dt_min_samples"), 2), 2),
        "rf_estimators": max(parse_optional_int(form.get("rf_estimators"), 100), 10),
        "rf_max_depth": parse_optional_int(form.get("rf_max_depth")),
    }


def ensure_runtime_dirs():
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def validate_training_dataframe(df):
    missing = [column for column in REQUIRED_DATASET_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required column(s): {', '.join(missing)}")

    frame = df[REQUIRED_DATASET_COLUMNS].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    for column in REQUIRED_DATASET_COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=REQUIRED_DATASET_COLUMNS).sort_values("Date")
    if len(frame) < 20:
        raise ValueError("Dataset must contain at least 20 valid OHLCV rows for train/test evaluation.")
    return frame


def load_csv_dataframe(path_or_file):
    return validate_training_dataframe(pd.read_csv(path_or_file))


def prepare_training_frame(df, horizon_days=1):
    frame = df[["Date", "Close"]].copy()
    for lag in range(1, 7):
        frame[f"lag_{lag}"] = frame["Close"].shift(lag)
    frame["target"] = frame["Close"].shift(-horizon_days)
    frame = frame.dropna().reset_index(drop=True)
    if len(frame) < 10:
        raise ValueError("Dataset does not have enough valid rows after lag feature generation.")
    return frame


def evaluate_model(model, x_test, y_test):
    predictions = model.predict(x_test)
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_test, predictions))),
        "mae": float(mean_absolute_error(y_test, predictions)),
        "r2": float(r2_score(y_test, predictions)),
    }


def next_model_id(state):
    return max((item.get("id", 0) for item in state.get("model_registry", [])), default=0) + 1


def dump_model(model, symbol, model_name):
    ensure_runtime_dirs()
    version = f"{symbol.lower()}_{model_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    artifact_name = f"{version}.pkl"
    model_path = os.path.join(MODEL_DIR, artifact_name)
    with open(model_path, "wb") as model_file:
        pickle.dump(model, model_file)
    return version, artifact_name, model_path


def train_models_from_dataframe(state, df, target_models, params, dataset_source, symbol="BTC"):
    frame = prepare_training_frame(df)
    feature_columns = [f"lag_{idx}" for idx in range(1, 7)]
    x_data = frame[feature_columns]
    y_data = frame["target"]
    x_train, x_test, y_train, y_test = train_test_split(
        x_data,
        y_data,
        test_size=0.2,
        shuffle=True,
        random_state=42,
    )

    registry_rows = state.setdefault("model_registry", [])
    metrics_state = state.setdefault("scientist_metrics", {})
    trained_at = now_str()
    current_id = next_model_id(state)
    results = {}

    for model_name in target_models:
        if model_name == "dt":
            model_params = {
                "random_state": 42,
                "max_depth": params["dt_max_depth"],
                "min_samples_split": params["dt_min_samples"],
            }
            model = DecisionTreeRegressor(**model_params)
            formatted_params = (
                f"Min Split: {params['dt_min_samples']} | "
                f"Depth: {format_optional_depth(params['dt_max_depth'])}"
            )
        elif model_name == "rf":
            model_params = {
                "random_state": 42,
                "n_estimators": params["rf_estimators"],
                "max_depth": params["rf_max_depth"],
            }
            model = RandomForestRegressor(**model_params)
            formatted_params = (
                f"Trees: {params['rf_estimators']} | "
                f"Depth: {format_optional_depth(params['rf_max_depth'])}"
            )
        else:
            continue

        model.fit(x_train, y_train)
        metrics = evaluate_model(model, x_test, y_test)
        version, artifact_name, model_path = dump_model(model, symbol, model_name)
        registry_rows.insert(
            0,
            {
                "id": current_id,
                "version": version,
                "trained_at": trained_at,
                "model_name": model_name,
                "formatted_params": formatted_params,
                "rmse": metrics["rmse"],
                "mae": metrics["mae"],
                "r2": metrics["r2"],
                "artifact_name": artifact_name,
                "model_path": model_path,
                "dataset_source": dataset_source,
            },
        )
        current_id += 1
        metrics_state[f"{model_name}_rmse"] = f"{metrics['rmse']:,.2f}"
        metrics_state[f"{model_name}_mae"] = f"{metrics['mae']:,.2f}"
        metrics_state[f"{model_name}_r2"] = f"{metrics['r2']:.4f}"
        results[model_name] = {"metrics": metrics, "artifact_name": artifact_name}

        if model_name == "rf":
            importances = getattr(model, "feature_importances_", np.zeros(6))
            state["feature_importance"] = {
                "labels": FEATURE_LABELS,
                "values": [round(float(item), 6) for item in importances.tolist()],
            }

    del registry_rows[20:]
    metrics_state["last_trained"] = datetime.now().strftime("%d/%m/%Y")
    return results


def has_real_model_registry(state):
    for row in state.get("model_registry", []):
        model_path = row.get("model_path")
        if model_path and os.path.exists(model_path):
            return True
    return False


def ensure_real_scientist_state(state):
    if has_real_model_registry(state):
        return False

    csv_path = os.path.join(BASE_DIR, "BTC-USD.csv")
    if not os.path.exists(csv_path):
        return False

    df = load_csv_dataframe(csv_path)
    state["model_registry"] = []
    params = {
        "dt_max_depth": None,
        "dt_min_samples": 2,
        "rf_estimators": 100,
        "rf_max_depth": None,
    }
    train_models_from_dataframe(
        state,
        df,
        target_models=["dt", "rf"],
        params=params,
        dataset_source="BTC-USD.csv",
        symbol="BTC",
    )
    add_audit_log(state, "Initialized real scientist model registry from BTC-USD.csv")
    return True


def normalize_notifications_for_scientist(notifications):
    rows = []
    for item in notifications:
        row = deepcopy(item)
        row["level"] = row.get("type", "info")
        rows.append(row)
    return rows


def build_drift_alert(metrics, notifications):
    unread_warnings = [
        item
        for item in notifications
        if item.get("type") == "warning" and not item.get("read", False)
    ]
    try:
        rf_r2 = float(metrics.get("rf_r2", 1))
        dt_r2 = float(metrics.get("dt_r2", 1))
    except (TypeError, ValueError):
        rf_r2 = 1
        dt_r2 = 1

    has_alert = bool(unread_warnings) or rf_r2 < 0.9 or dt_r2 < 0.85
    title = (
        "System Alert: Potential Data Drift Detected"
        if has_alert
        else "System Monitor: Models Within Acceptable Range"
    )
    automated_message = (
        f"Latest BTC/USD evaluation shows RF RMSE {metrics.get('rf_rmse', 'N/A')}, "
        f"DT RMSE {metrics.get('dt_rmse', 'N/A')}, RF R2 {metrics.get('rf_r2', 'N/A')}, "
        f"DT R2 {metrics.get('dt_r2', 'N/A')}."
    )
    admin_message = (
        "Retraining is recommended when warnings remain unread or R2 degrades."
        if has_alert
        else "The latest local metrics are inside the expected operating range."
    )
    return {
        "has_alert": has_alert,
        "title": title,
        "automated_message": automated_message,
        "admin_message": admin_message,
        "level": "warning" if has_alert else "info",
    }


def build_registry_rows(state):
    rows = deepcopy(state.get("model_registry", []))
    for row in rows:
        row["download_url"] = url_for("download_model_artifact", model_id=row["id"])
    return rows[:10]


def count_api_requests(request_metrics):
    return request_metrics.get("total_requests", 0)


def count_monitored_coins():
    return len(
        [
            filename
            for filename in os.listdir(BASE_DIR)
            if filename.endswith("-USD.csv")
        ]
    )


def build_traffic_chart_data(request_metrics):
    today = datetime.now().date()
    last_7_days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    daily_counts = request_metrics.get("daily_counts", {})
    counts_by_day = {
        day: daily_counts.get(day.strftime("%Y-%m-%d"), 0)
        for day in last_7_days
    }

    return {
        "labels": [day.strftime("%d/%m") for day in last_7_days],
        "values": [counts_by_day[day] for day in last_7_days],
    }


def build_prediction_distribution(audit_logs):
    btc_count = 0
    eth_count = 0

    for log in audit_logs:
        event = log.get("event", "").upper()
        if "PREDICTED BTC" in event:
            btc_count += 1
        if "PREDICTED ETH" in event:
            eth_count += 1

    return {
        "labels": ["Bitcoin (BTC)", "Ethereum (ETH)"],
        "values": [btc_count, eth_count],
    }


def record_system_request(state):
    metrics = state.setdefault(
        "request_metrics",
        {
            "total_requests": 0,
            "daily_counts": {},
        },
    )
    metrics["total_requests"] = metrics.get("total_requests", 0) + 1

    today_key = datetime.now().strftime("%Y-%m-%d")
    daily_counts = metrics.setdefault("daily_counts", {})
    daily_counts[today_key] = daily_counts.get(today_key, 0) + 1

    cutoff_key = (datetime.now().date() - timedelta(days=30)).strftime("%Y-%m-%d")
    metrics["daily_counts"] = {
        day: count
        for day, count in daily_counts.items()
        if day >= cutoff_key
    }


def admin_required():
    return "role" in session and session["role"] == "admin"


def scientist_required():
    return "role" in session and session["role"] == "scientist"


def filter_admin_data(state, search_query):
    normalized_query = search_query.strip().lower()
    users = build_admin_users(state["users"])
    audit_logs = deepcopy(state["audit_logs"])

    if not normalized_query:
        return users, audit_logs

    users = [
        user
        for user in users
        if normalized_query in user["username"].lower()
        or normalized_query in user["display_name"].lower()
        or normalized_query in user["email"].lower()
        or normalized_query in user["role_label"].lower()
    ]
    audit_logs = [
        log
        for log in audit_logs
        if normalized_query in log["event"].lower()
        or normalized_query in log["status"].lower()
        or normalized_query in log["timestamp"].lower()
    ]
    return users, audit_logs


def build_admin_dashboard_payload(state):
    stats = {
        "active_users": len(state["users"]),
        "api_requests": count_api_requests(state["request_metrics"]),
        "monitored_coins": count_monitored_coins(),
        "system_status": "Online",
    }

    return {
        "stats": stats,
        "traffic_chart": build_traffic_chart_data(state["request_metrics"]),
        "prediction_distribution": build_prediction_distribution(state["audit_logs"]),
    }


@app.before_request
def track_request_metrics():
    if request.endpoint == "static" or request.method == "OPTIONS":
        return

    state = read_state()
    record_system_request(state)
    write_state(state)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        state = read_state()
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]
        user = state["users"].get(username)

        if user and user["password"] == password and user["role"] == role:
            session["role"] = user["role"]
            session["username"] = username
            user["last_login"] = now_str()
            add_audit_log(
                state,
                f"Successful login for {username} ({role_label(role)})",
            )
            write_state(state)

            if role == "admin":
                return redirect(url_for("admin_dashboard"))
            if role == "scientist":
                return redirect(url_for("scientist_dashboard"))
            return redirect(url_for("home"))

        add_audit_log(
            state,
            f"Failed login attempt (username: {username})",
            status="Warning",
        )
        write_state(state)
        return render_template(
            "login.html",
            error="Invalid username, password, or role!",
        )

    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    username = session.get("username")
    if username:
        state = read_state()
        add_audit_log(state, f"User {username} logged out")
        write_state(state)
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["POST", "GET"])
def home():
    if "role" not in session:
        return redirect(url_for("login"))

    return render_template("user.html")


@app.route("/predict/", methods=["POST"])
def predict():
    if "role" not in session:
        return redirect(url_for("login"))

    stock_type = request.form.get("stock_type", "BTC")
    next_time_str = request.form.get("next_time", "1")
    model_choice = request.form.get("model_choice", "both")

    try:
        days = int(next_time_str)
    except ValueError:
        days = 1

    tree_result, rf_result = TreePredict.PredictValue(stock_type, days)

    state = read_state()
    add_audit_log(
        state,
        f"User {session.get('username', 'unknown')} predicted {stock_type} ({days} days)",
    )
    write_state(state)

    labels_1 = ["T-5", "T-4", "T-3", "T-2", "T-1", "Today"]
    labels_2 = labels_1 + [f"Day +{days}"]

    return render_template(
        "test.html",
        labels_1=labels_1,
        data_1=tree_result[:6].tolist(),
        labels_2=labels_2,
        data_2=tree_result.tolist(),
        data_rf=rf_result.tolist(),
        CurrentValue="{:,.2f}".format(tree_result[5]),
        PredictValue_DT="{:,.2f}".format(tree_result[6]),
        PredictValue_RF="{:,.2f}".format(rf_result[6]),
        model_choice=model_choice,
        next_time=days,
    )


@app.route("/admin_dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("login"))

    state = read_state()
    search_query = request.args.get("q", "").strip()
    users, audit_logs = filter_admin_data(state, search_query)

    dashboard_payload = build_admin_dashboard_payload(state)

    return render_template(
        "admin.html",
        users=users,
        audit_logs=audit_logs[:12],
        stats=dashboard_payload["stats"],
        traffic_chart=dashboard_payload["traffic_chart"],
        prediction_distribution=dashboard_payload["prediction_distribution"],
        search_query=request.args.get("q", "").strip(),
    )


@app.route("/admin/dashboard-metrics")
def admin_dashboard_metrics():
    if not admin_required():
        return jsonify({"ok": False, "message": "Unauthorized"}), 401

    state = read_state()
    return jsonify(
        {
            "ok": True,
            **build_admin_dashboard_payload(state),
        }
    )


@app.route("/admin/audit-logs")
def search_audit_logs():
    if not admin_required():
        return jsonify({"ok": False, "message": "Unauthorized"}), 401

    state = read_state()
    search_query = request.args.get("q", "").strip()
    _, audit_logs = filter_admin_data(state, search_query)
    return jsonify(
        {
            "ok": True,
            "search_query": search_query,
            "logs": audit_logs[:12],
        }
    )


@app.route("/admin/users", methods=["POST"])
def add_user():
    if not admin_required():
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Unauthorized"}), 401
        return redirect(url_for("login"))

    state = read_state()
    username = request.form.get("username", "").strip()
    display_name = request.form.get("display_name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "user").strip()

    if not all([username, display_name, email, password, role]):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Please fill in all fields before creating a user."}), 400
        flash("Please fill in all fields before creating a user.", "error")
        return redirect(url_for("admin_dashboard"))

    if role not in ROLE_LABELS:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Selected role is not valid."}), 400
        flash("Selected role is not valid.", "error")
        return redirect(url_for("admin_dashboard"))

    if username in state["users"]:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": f"Username '{username}' already exists."}), 400
        flash(f"Username '{username}' already exists.", "error")
        return redirect(url_for("admin_dashboard"))

    if any(user["email"].lower() == email.lower() for user in state["users"].values()):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": f"Email '{email}' is already in use."}), 400
        flash(f"Email '{email}' is already in use.", "error")
        return redirect(url_for("admin_dashboard"))

    state["users"][username] = {
        "password": password,
        "role": role,
        "display_name": display_name,
        "email": email,
        "last_login": "Never",
    }
    add_audit_log(
        state,
        f"Admin created user {username} with role {role_label(role)}",
    )
    write_state(state)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            {
                "ok": True,
                "message": f"User '{username}' was created successfully.",
                "category": "success",
                "user": {
                    "username": username,
                    "display_name": display_name,
                    "email": email,
                    "role": role,
                    "role_label": role_label(role),
                    "last_login": "Never",
                    "protected": False,
                },
                "active_users": len(state["users"]),
            }
        )
    flash(f"User '{username}' was created successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<username>/role", methods=["POST"])
def update_user_role(username):
    if not admin_required():
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Unauthorized"}), 401
        return redirect(url_for("login"))

    state = read_state()
    user = state["users"].get(username)
    new_role = request.form.get("role", "").strip()

    if not user:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "User does not exist anymore."}), 404
        flash("User does not exist anymore.", "error")
        return redirect(url_for("admin_dashboard"))

    if new_role not in ROLE_LABELS:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Selected role is not valid."}), 400
        flash("Selected role is not valid.", "error")
        return redirect(url_for("admin_dashboard"))

    old_role = user["role"]
    if old_role == new_role:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                {
                    "ok": True,
                    "message": f"Role for '{username}' is already {role_label(new_role)}.",
                    "role": new_role,
                    "role_label": role_label(new_role),
                    "category": "info",
                }
            )
        flash(f"Role for '{username}' is already {role_label(new_role)}.", "info")
        return redirect(url_for("admin_dashboard"))

    user["role"] = new_role
    add_audit_log(
        state,
        f"Admin changed role for {username} from {role_label(old_role)} to {role_label(new_role)}",
    )
    write_state(state)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            {
                "ok": True,
                "message": f"Updated role for '{username}' to {role_label(new_role)}.",
                "role": new_role,
                "role_label": role_label(new_role),
                "category": "success",
            }
        )
    flash(f"Updated role for '{username}' to {role_label(new_role)}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<username>/delete", methods=["POST"])
def delete_user(username):
    if not admin_required():
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Unauthorized"}), 401
        return redirect(url_for("login"))

    state = read_state()
    user = state["users"].get(username)

    if not user:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "User does not exist anymore."}), 404
        flash("User does not exist anymore.", "error")
        return redirect(url_for("admin_dashboard"))

    if username == "admin":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "The default admin account is protected and cannot be deleted."}), 400
        flash("The default admin account is protected and cannot be deleted.", "error")
        return redirect(url_for("admin_dashboard"))

    if username == session.get("username"):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "You cannot delete the account currently in use."}), 400
        flash("You cannot delete the account currently in use.", "error")
        return redirect(url_for("admin_dashboard"))

    admin_count = sum(1 for item in state["users"].values() if item["role"] == "admin")
    if user["role"] == "admin" and admin_count <= 1:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "At least one System Admin account must remain in the system."}), 400
        flash("At least one System Admin account must remain in the system.", "error")
        return redirect(url_for("admin_dashboard"))

    del state["users"][username]
    add_audit_log(state, f"Admin deleted user {username}")
    write_state(state)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            {
                "ok": True,
                "message": f"User '{username}' was deleted.",
                "category": "success",
                "username": username,
                "active_users": len(state["users"]),
            }
        )
    flash(f"User '{username}' was deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/notify", methods=["POST"])
def notify_scientists():
    if not admin_required():
        return redirect(url_for("login"))

    state = read_state()
    message = request.form.get("message", "").strip()
    if not message:
        flash("Notification message cannot be empty.", "error")
        return redirect(url_for("admin_dashboard"))

    state["notifications"].insert(
        0,
        {
            "id": next_notification_id(state["notifications"]),
            "type": "admin",
            "title": "Admin Message",
            "message": message,
            "sender": session.get("username", "admin"),
            "created_at": now_str(),
            "read": False,
        },
    )
    add_audit_log(state, "Admin sent a message to the Data Scientist dashboard")
    write_state(state)
    flash("Notification sent to the Data Scientist dashboard.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/scientist_dashboard")
def scientist_dashboard():
    if not scientist_required():
        return redirect(url_for("login"))

    state = read_state()
    try:
        if ensure_real_scientist_state(state):
            write_state(state)
    except ValueError as exc:
        session["latest_retrain_error"] = str(exc)
    notifications = state["notifications"]
    unread_count = sum(1 for item in notifications if not item.get("read", False))
    latest_notice = session.pop("latest_retrain_notice", None)
    retrain_error = session.pop("latest_retrain_error", None)

    return render_template(
        "scientist.html",
        metrics=state["scientist_metrics"],
        notifications=normalize_notifications_for_scientist(notifications[:5]),
        unread_count=unread_count,
        latest_notice=latest_notice,
        retrain_error=retrain_error,
        drift_alert=build_drift_alert(state["scientist_metrics"], notifications),
        scientist=current_scientist(state),
        registry_rows=build_registry_rows(state),
        feature_labels=state["feature_importance"]["labels"],
        feature_values=state["feature_importance"]["values"],
        selected_symbol="BTC",
    )


@app.route("/retrain/result")
def retrain_result():
    if not scientist_required():
        return redirect(url_for("login"))

    summary = session.get("latest_retrain_result")
    if not summary:
        return redirect(url_for("scientist_dashboard"))
    return render_template("retrain_result.html", summary=summary)


@app.route("/scientist/notifications/read", methods=["POST"])
def mark_all_scientist_notifications_read():
    if not scientist_required():
        return redirect(url_for("login"))

    state = read_state()
    for notification in state["notifications"]:
        notification["read"] = True
    add_audit_log(state, "Scientist marked all notifications as read")
    write_state(state)
    return ("", 204)


@app.route("/scientist/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    if not scientist_required():
        return redirect(url_for("login"))

    state = read_state()
    notification = next(
        (item for item in state["notifications"] if item["id"] == notification_id),
        None,
    )
    if notification:
        notification["read"] = True
        add_audit_log(
            state,
            f"Scientist marked notification #{notification_id} as read",
        )
        write_state(state)
        flash("Notification marked as read.", "success")

    return redirect(url_for("scientist_dashboard"))


@app.route("/scientist/models/<int:model_id>/download")
def download_model_artifact(model_id):
    if not scientist_required():
        return redirect(url_for("login"))

    state = read_state()
    row = next(
        (item for item in state.get("model_registry", []) if item["id"] == model_id),
        None,
    )
    if not row:
        session["latest_retrain_error"] = "Model artifact record was not found."
        return redirect(url_for("scientist_dashboard"))

    model_path = row.get("model_path")
    if model_path and os.path.exists(model_path):
        return send_file(model_path, as_attachment=True, download_name=row["artifact_name"])

    session["latest_retrain_error"] = "Model artifact file was not found on disk."
    return redirect(url_for("scientist_dashboard"))


@app.route("/retrain", methods=["POST"])
def retrain_model():
    if not scientist_required():
        return redirect(url_for("login"))

    dataset_file = request.files.get("dataset_file")
    target_model = request.form.get("target_model", "both")
    state = read_state()

    if not dataset_file or not dataset_file.filename.lower().endswith(".csv"):
        message = "Please upload a valid CSV file before retraining."
        session["latest_retrain_error"] = message
        return jsonify({"error": message, "redirect_url": url_for("scientist_dashboard")}), 400

    if target_model not in {"dt", "rf", "both"}:
        message = "Please choose a valid target model."
        session["latest_retrain_error"] = message
        return jsonify({"error": message, "redirect_url": url_for("scientist_dashboard")}), 400

    trained_at = now_str()
    target_models = ["dt", "rf"] if target_model == "both" else [target_model]
    safe_name = secure_filename(dataset_file.filename)
    if not safe_name:
        message = "Uploaded dataset filename is not valid."
        session["latest_retrain_error"] = message
        return jsonify({"error": message, "redirect_url": url_for("scientist_dashboard")}), 400

    saved_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    ensure_runtime_dirs()
    upload_path = os.path.join(UPLOAD_DIR, saved_name)

    try:
        dataset_file.save(upload_path)
        df = load_csv_dataframe(upload_path)
        params = parse_retrain_params(request.form)
        results = train_models_from_dataframe(
            state,
            df,
            target_models=target_models,
            params=params,
            dataset_source=saved_name,
            symbol=request.form.get("asset_symbol", "BTC").upper(),
        )
    except (OSError, ValueError, KeyError) as exc:
        message = str(exc)
        session["latest_retrain_error"] = message
        return jsonify({"error": message, "redirect_url": url_for("scientist_dashboard")}), 400

    state["notifications"].insert(
        0,
        {
            "id": next_notification_id(state["notifications"]),
            "type": "info",
            "title": "Retraining completed",
            "message": f"Models retrained for BTC: {', '.join(results.keys()).upper()}",
            "sender": "Pipeline",
            "created_at": trained_at,
            "read": False,
        },
    )
    add_audit_log(
        state,
        f"Scientist retrained model(s): {target_model} using dataset {dataset_file.filename}",
    )
    write_state(state)
    session["latest_retrain_notice"] = {
        "message": f"Models retrained for BTC: {', '.join(results.keys()).upper()}",
        "time": trained_at,
    }
    session["latest_retrain_result"] = {
        "file_name": dataset_file.filename,
        "saved_name": saved_name,
        "target_model": target_model.upper(),
        "trained_at": trained_at,
        "dt_max_depth": format_optional_depth(request.form.get("dt_max_depth")),
        "dt_min_samples": request.form.get("dt_min_samples") or "2",
        "rf_estimators": request.form.get("rf_estimators") or "100",
        "rf_max_depth": format_optional_depth(request.form.get("rf_max_depth")),
    }
    return jsonify(
        {
            "message": "Model retraining completed successfully.",
            "results": results,
            "redirect_url": url_for("retrain_result"),
        }
    )


if __name__ == "__main__":
    ensure_state_file()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug, use_reloader=True)
