import io
import json
import os
from functools import wraps
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from database import (
    add_audit,
    add_feedback,
    add_notification,
    add_prediction,
    delete_user,
    get_user,
    init_db,
    list_assets,
    list_audit_logs,
    list_feedback_reports,
    list_notifications,
    list_users,
    mark_notifications_read,
    prediction_distribution,
    prediction_traffic,
    unread_notification_count,
    update_user,
    utc_now,
)
from services.market_service import MarketService
from services.model_service import ModelService


app = Flask(__name__)
app.config.from_object(Config)
init_db(app)


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                return redirect(url_for("home"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def current_user():
    if "user_id" not in session:
        return None
    return {
        "id": session["user_id"],
        "username": session["username"],
        "role": session["role"],
        "full_name": session["full_name"],
    }


def market_service():
    return MarketService(app.config)


def model_service():
    return ModelService(app.config)


def parse_optional_int(value):
    if value in (None, "", "-"):
        return None
    return int(value)


def upload_dir():
    path = Path(app.config["UPLOAD_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_model_params(params_json, model_name):
    params = json.loads(params_json or "{}")
    if model_name == "rf":
        estimators = params.get("n_estimators", "Auto")
        depth = params.get("max_depth")
        return f"Trees: {estimators} | Depth: {depth if depth is not None else 'Auto'}"
    depth = params.get("max_depth")
    min_split = params.get("min_samples_split", 2)
    return f"Min Split: {min_split} | Depth: {depth if depth is not None else 'Auto'}"


def build_drift_alert(metrics, symbol):
    feedback_count = len(list_feedback_reports(status="open"))
    prediction_count = len([row for row in prediction_traffic(limit=7)])
    rf = metrics.get("rf", {})
    dt = metrics.get("dt", {})
    rf_r2 = rf.get("r2", 1)
    dt_r2 = dt.get("r2", 1)
    rf_rmse = rf.get("rmse", 0)
    dt_rmse = dt.get("rmse", 0)

    has_alert = feedback_count > 0 or rf_r2 < 0.9 or dt_r2 < 0.85
    title = "System Alert: Potential Data Drift Detected" if has_alert else "System Monitor: Models Within Acceptable Range"
    automated_message = (
        f"The latest {symbol}/USD evaluation shows RF RMSE {rf_rmse:,.2f}, DT RMSE {dt_rmse:,.2f}, "
        f"RF R2 {rf_r2:.4f}, DT R2 {dt_r2:.4f}. Open feedback reports: {feedback_count}."
    )
    admin_message = (
        f"Prediction activity observed on {prediction_count} recent day bucket(s). "
        "Retraining is recommended when feedback rises or R2 degrades."
    )
    return {
        "has_alert": has_alert,
        "title": title,
        "automated_message": automated_message,
        "admin_message": admin_message,
        "level": "warning" if has_alert else "info",
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"].strip()
        user = get_user(username, role)

        if user and check_password_hash(user["password_hash"], password):
            update_user(username, last_login_at=utc_now())
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            add_audit(user["username"], user["role"], "login", f"User {user['username']} logged in")
            if role == "admin":
                return redirect(url_for("admin_dashboard"))
            if role == "scientist":
                return redirect(url_for("scientist_dashboard"))
            return redirect(url_for("home"))

        add_audit(username or "anonymous", role or "unknown", "login_failed", f"Failed login attempt for {username}", "warning")
        return render_template("login.html", error="Invalid username, password, or role.", default_passwords=_default_passwords())

    return render_template("login.html", default_passwords=_default_passwords())


@app.route("/logout")
def logout():
    user = current_user()
    if user:
        add_audit(user["username"], user["role"], "logout", f"User {user['username']} logged out")
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
@role_required("user", "admin", "scientist")
def home():
    svc = market_service()
    assets = svc.list_assets()
    selected_symbol = request.args.get("symbol", "BTC").upper()
    try:
        svc.sync_market_data(selected_symbol)
    except Exception:
        pass
    try:
        svc.sync_news_from_feed(limit=6)
    except Exception:
        pass
    return render_template(
        "user.html",
        assets=assets,
        selected_symbol=selected_symbol,
        market_summary=svc.get_market_summary(selected_symbol),
        market_news=svc.get_latest_news(limit=3),
        user=current_user(),
        predict_error=session.pop("predict_error", None),
    )


@app.route("/predict/", methods=["POST"])
@role_required("user", "admin", "scientist")
def predict():
    stock_type = request.form.get("stock_type", "BTC").upper()
    model_choice = request.form.get("model_choice", "both")
    next_time_raw = request.form.get("next_time", "1")
    if next_time_raw not in {"1", "5", "10"}:
        session["predict_error"] = "Please choose a valid prediction horizon."
        return redirect(url_for("home", symbol=stock_type) + "#section--2")
    days = int(next_time_raw)
    result = model_service().predict(stock_type, days=days)
    user = current_user()
    log = add_prediction(
        {
            "user_id": user["id"],
            "asset_symbol": stock_type,
            "horizon_days": days,
            "model_choice": model_choice,
            "current_price": result["current_price"],
            "dt_prediction": result["dt_prediction"],
            "rf_prediction": result["rf_prediction"],
            "created_at": utc_now(),
            "status": "success",
        }
    )
    add_audit(user["username"], user["role"], "prediction", f"{user['username']} predicted {stock_type} for {days} day(s)")
    return render_template(
        "test.html",
        labels_1=result["labels_current"],
        data_1=result["history"],
        labels_2=result["labels_prediction"],
        data_2=result["dt_series"],
        data_rf=result["rf_series"],
        CurrentValue="{:,.2f}".format(result["current_price"]),
        PredictValue_DT="{:,.2f}".format(result["dt_prediction"]),
        PredictValue_RF="{:,.2f}".format(result["rf_prediction"]),
        model_choice=model_choice,
        next_time=days,
        asset_symbol=stock_type,
        prediction_log_id=log["id"],
    )


@app.route("/about")
@role_required("user", "admin", "scientist")
def about_page():
    return render_template(
        "basic_page.html",
        title="About",
        heading="About CryptoPredict",
        body="CryptoPredict is an educational cryptocurrency forecasting application that combines stored market data, retraining workflows, and interactive dashboards for different stakeholder roles.",
    )


@app.route("/terms")
@role_required("user", "admin", "scientist")
def terms_page():
    return render_template(
        "basic_page.html",
        title="Terms of Use",
        heading="Terms of Use",
        body="This application is provided for educational and research purposes. Forecasts are model outputs, not financial advice, and should not be treated as investment recommendations.",
    )


@app.route("/privacy")
@role_required("user", "admin", "scientist")
def privacy_page():
    return render_template(
        "basic_page.html",
        title="Privacy Policy",
        heading="Privacy Policy",
        body="The system stores authentication details, prediction requests, audit logs, feedback reports, notifications, and uploaded retraining datasets for application operation and academic review.",
    )


@app.route("/contact")
@role_required("user", "admin", "scientist")
def contact_page():
    return render_template(
        "basic_page.html",
        title="Contact",
        heading="Contact",
        body="For academic questions or application issues, contact the project team through the HCMUT course channel or the system administrator account configured in this environment.",
    )


@app.route("/feedback", methods=["POST"])
@role_required("user", "admin", "scientist")
def feedback():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message", "").strip() or "Prediction result flagged by user."
    prediction_log_id = payload.get("prediction_log_id")
    user = current_user()
    add_feedback(prediction_log_id, user["username"], message)
    add_notification("scientist", "Prediction feedback received", f"User {user['username']} reported a prediction issue.", "warning")
    add_audit(user["username"], user["role"], "feedback", f"{user['username']} submitted prediction feedback")
    return jsonify({"message": "Feedback has been logged for the data science team."})


@app.route("/admin_dashboard")
@role_required("admin")
def admin_dashboard():
    users = list_users()
    stats = {
        "active_users": len(users),
        "api_requests": sum(item["total"] for item in prediction_traffic(limit=365)),
        "monitored_coins": len(list_assets()),
        "system_status": "Online",
    }
    return render_template(
        "admin.html",
        stats=stats,
        users=users,
        logs=list_audit_logs(limit=8),
        traffic=list(reversed(prediction_traffic(limit=7))),
        distribution=prediction_distribution(),
        admin=current_user(),
    )


@app.route("/admin/users/<username>/role", methods=["POST"])
@role_required("admin")
def update_user_role(username):
    payload = request.get_json(silent=True) or {}
    new_role = payload.get("role")
    if new_role not in {"admin", "scientist", "user"}:
        return jsonify({"error": "Invalid role"}), 400
    if update_user(username, role=new_role) is None:
        return jsonify({"error": "User not found"}), 404
    add_audit(session["username"], session["role"], "role_update", f"Updated {username} role to {new_role}")
    return jsonify({"message": "User role updated."})


@app.route("/admin/users/<username>", methods=["DELETE"])
@role_required("admin")
def remove_user(username):
    if username == session["username"]:
        return jsonify({"error": "You cannot delete the current admin account."}), 400
    if not delete_user(username):
        return jsonify({"error": "User not found"}), 404
    add_audit(session["username"], session["role"], "user_delete", f"Deleted user {username}")
    return jsonify({"message": "User deleted."})


@app.route("/admin/ping-ds", methods=["POST"])
@role_required("admin")
def ping_ds():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message", "").strip()
    if not message:
        return jsonify({"error": "Message is required"}), 400
    add_notification("scientist", "Admin alert", message, "warning")
    add_audit(session["username"], session["role"], "ping_ds", f"Admin sent DS alert: {message}")
    return jsonify({"message": "Alert sent to Data Scientist team."})


@app.route("/scientist_dashboard")
@role_required("scientist")
def scientist_dashboard():
    svc = model_service()
    symbol = request.args.get("symbol", "BTC").upper()
    metrics = svc.get_latest_metrics(symbol)
    if not metrics:
        svc.train_and_register(symbol, target_model="both", horizon_days=1)
        metrics = svc.get_latest_metrics(symbol)

    rf_metrics = metrics.get("rf", {})
    feature_values = json.loads(rf_metrics.get("feature_importances_json", "[]"))
    feature_labels = [f"T-{idx}" for idx in range(1, len(feature_values) + 1)]
    latest_notice = session.pop("latest_retrain_notice", None)
    retrain_error = session.pop("latest_retrain_error", None)

    dt_metrics = metrics.get("dt", {})
    rf_metrics = metrics.get("rf", {})
    dashboard_metrics = {
        "dt_rmse": "{:,.2f}".format(dt_metrics.get("rmse", 0)),
        "dt_mae": "{:,.2f}".format(dt_metrics.get("mae", 0)),
        "dt_r2": "{:.4f}".format(dt_metrics.get("r2", 0)),
        "rf_rmse": "{:,.2f}".format(rf_metrics.get("rmse", 0)),
        "rf_mae": "{:,.2f}".format(rf_metrics.get("mae", 0)),
        "rf_r2": "{:.4f}".format(rf_metrics.get("r2", 0)),
        "last_trained": rf_metrics.get("trained_at") or dt_metrics.get("trained_at") or "N/A",
    }
    registry_rows = svc.get_model_registry(symbol=symbol, limit=10)
    for row in registry_rows:
        row["formatted_params"] = format_model_params(row.get("params_json"), row.get("model_name"))
        row["artifact_name"] = Path(row.get("model_path", "")).name
        row["download_url"] = url_for("download_model_artifact", model_id=row["id"])

    return render_template(
        "scientist.html",
        metrics=dashboard_metrics,
        selected_symbol=symbol,
        registry_rows=registry_rows,
        notifications=list_notifications("scientist", limit=5),
        unread_notifications=unread_notification_count("scientist"),
        feature_labels=feature_labels,
        feature_values=feature_values,
        scientist=current_user(),
        latest_notice=latest_notice,
        retrain_error=retrain_error,
        drift_alert=build_drift_alert(metrics, symbol),
    )


@app.route("/retrain/result")
@role_required("scientist")
def retrain_result():
    summary = session.get("latest_retrain_result")
    if not summary:
        return redirect(url_for("scientist_dashboard"))
    return render_template("retrain_result.html", summary=summary)


@app.route("/scientist/notifications/read", methods=["POST"])
@role_required("scientist")
def scientist_notifications_read():
    mark_notifications_read("scientist")
    return jsonify({"message": "Notifications marked as read."})


@app.route("/scientist/models/<int:model_id>/download")
@role_required("scientist")
def download_model_artifact(model_id):
    rows = model_service().get_model_registry(limit=200)
    row = next((item for item in rows if item["id"] == model_id), None)
    if row is None:
        return redirect(url_for("scientist_dashboard"))
    model_path = Path(row["model_path"])
    if not model_path.exists():
        session["latest_retrain_error"] = "Model artifact file was not found on disk."
        return redirect(url_for("scientist_dashboard"))
    return send_file(model_path, as_attachment=True, download_name=model_path.name)


@app.route("/retrain", methods=["POST"])
@role_required("scientist")
def retrain_model():
    file = request.files.get("dataset_file")
    target_model = request.form.get("target_model", "both")
    symbol = request.form.get("asset_symbol", "BTC").upper()
    params = {
        "dt_max_depth": parse_optional_int(request.form.get("dt_max_depth")),
        "dt_min_samples": parse_optional_int(request.form.get("dt_min_samples")) or 2,
        "rf_estimators": parse_optional_int(request.form.get("rf_estimators")) or 100,
        "rf_max_depth": parse_optional_int(request.form.get("rf_max_depth")),
    }

    uploaded_df = None
    saved_name = "No uploaded file"
    if file and file.filename:
        raw_bytes = file.read()
        uploaded_df = pd.read_csv(io.BytesIO(raw_bytes))
        required_columns = {"Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"}
        if not required_columns.issubset(uploaded_df.columns):
            session["latest_retrain_error"] = "Dataset file does not contain the required OHLCV columns."
            return jsonify({"error": "Dataset file does not contain the required OHLCV columns.", "redirect_url": url_for("scientist_dashboard", symbol=symbol)}), 400
        filename = secure_filename(file.filename)
        saved_name = f"{symbol.lower()}_{utc_now().replace(':', '-').replace('+00:00', 'z')}_{filename}"
        (upload_dir() / saved_name).write_bytes(raw_bytes)
        market_service().upsert_price_rows(
            symbol,
            [
                {
                    "trade_date": str(row["Date"]),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "adj_close": float(row["Adj Close"]),
                    "volume": float(row["Volume"]),
                }
                for _, row in uploaded_df.iterrows()
            ],
            source="uploaded_csv",
        )
    else:
        session["latest_retrain_error"] = "A CSV dataset file is required for retraining."
        return jsonify({"error": "A CSV dataset file is required for retraining.", "redirect_url": url_for("scientist_dashboard", symbol=symbol)}), 400

    results = model_service().train_and_register(symbol, target_model=target_model, uploaded_df=uploaded_df, params=params, horizon_days=1)
    message = f"Models retrained for {symbol}: {', '.join(results.keys()).upper()}"
    trained_at = utc_now()
    add_notification("scientist", "Retraining completed", message, "info")
    add_audit(session["username"], session["role"], "retrain", f"Retrained {target_model} model(s) for {symbol}")
    session["latest_retrain_notice"] = {
        "message": message,
        "time": trained_at,
    }
    session["latest_retrain_result"] = {
        "file_name": file.filename if file and file.filename else "No uploaded file",
        "saved_name": saved_name,
        "target_model": target_model.upper(),
        "trained_at": trained_at,
        "dt_max_depth": params["dt_max_depth"] if params["dt_max_depth"] is not None else "Auto",
        "dt_min_samples": params["dt_min_samples"],
        "rf_estimators": params["rf_estimators"],
        "rf_max_depth": params["rf_max_depth"] if params["rf_max_depth"] is not None else "Auto",
    }
    return jsonify({"message": "Model retraining completed successfully.", "results": results, "redirect_url": url_for("retrain_result")})


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "service": "crypto-predict"})


@app.route("/api/assets")
def api_assets():
    return jsonify({"assets": list_assets()})


@app.route("/api/market/<symbol>")
def api_market(symbol):
    svc = market_service()
    summary = svc.get_market_summary(symbol)
    if summary is None:
        return jsonify({"error": "Asset not found"}), 404
    return jsonify({"summary": summary, "series": svc.get_price_series(symbol, limit=30)})


@app.route("/api/predict", methods=["POST"])
def api_predict():
    payload = request.get_json(silent=True) or {}
    return jsonify(model_service().predict(payload.get("symbol", "BTC"), days=int(payload.get("days", 1))))


def _default_passwords():
    return {
        "admin": app.config["DEFAULT_ADMIN_PASSWORD"],
        "scientist": app.config["DEFAULT_SCIENTIST_PASSWORD"],
        "user": app.config["DEFAULT_USER_PASSWORD"],
    }


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5050")),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
