from copy import deepcopy
from datetime import datetime, timedelta
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
import json
import os
import threading
import time

import TreePredict

app = Flask(__name__)
app.secret_key = "super_secret_key_hcmut"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "app_state.json")
MAX_AUDIT_LOGS = 100
STATE_LOCK = threading.RLock()
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
            "rf_rmse": "850.75",
            "rf_mae": "610.30",
            "last_trained": "07/04/2026",
        },
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
        os.replace(temp_path, STATE_FILE)


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
    notifications = state["notifications"]
    unread_count = sum(1 for item in notifications if not item.get("read", False))

    return render_template(
        "scientist.html",
        metrics=state["scientist_metrics"],
        notifications=notifications[:8],
        unread_count=unread_count,
        latest_admin_notification=latest_admin_message(notifications),
    )


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


@app.route("/retrain", methods=["POST"])
def retrain_model():
    if not scientist_required():
        return redirect(url_for("login"))

    dataset_file = request.files.get("dataset_file")
    target_model = request.form.get("target_model", "both")
    state = read_state()

    if not dataset_file or not dataset_file.filename.lower().endswith(".csv"):
        flash("Please upload a valid CSV file before retraining.", "error")
        return redirect(url_for("scientist_dashboard"))

    time.sleep(1)
    state["scientist_metrics"]["last_trained"] = datetime.now().strftime("%d/%m/%Y")
    add_audit_log(
        state,
        f"Scientist retrained model(s): {target_model} using dataset {dataset_file.filename}",
    )
    write_state(state)
    flash("Retraining completed successfully.", "success")
    return redirect(url_for("scientist_dashboard"))


if __name__ == "__main__":
    ensure_state_file()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug, use_reloader=True)
