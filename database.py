import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg
from flask import current_app
from psycopg import sql
from psycopg import OperationalError
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash


DEFAULT_STORE = {
    "users": [],
    "assets": [],
    "price_history": [],
    "market_news": [],
    "model_registry": [],
    "prediction_logs": [],
    "feedback_reports": [],
    "notifications": [],
    "audit_logs": [],
    "sync_state": {},
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _schema_path():
    return Path(current_app.root_path) / "schema.sql"


def _connect():
    return psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)


def _normalize_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _normalize_row(row):
    if row is None:
        return None
    return {key: _normalize_value(value) for key, value in row.items()}


def _normalize_rows(rows):
    return [_normalize_row(row) for row in rows]


def _apply_schema(conn):
    schema_sql = _schema_path().read_text(encoding="utf-8")
    with conn.cursor() as cur:
        for statement in schema_sql.split(";\n"):
            statement = statement.strip()
            if statement:
                cur.execute(statement)


def _table_count(conn, table_name):
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) AS total FROM {}").format(sql.Identifier(table_name)))
        return cur.fetchone()["total"]


def _seed_assets(conn, root_path):
    assets = [
        {
            "symbol": "BTC",
            "name": "Bitcoin",
            "coingecko_id": "bitcoin",
            "csv_path": str(Path(root_path) / "BTC-USD.csv"),
        },
        {
            "symbol": "ETH",
            "name": "Ethereum",
            "coingecko_id": "ethereum",
            "csv_path": str(Path(root_path) / "ETH-USD.csv"),
        },
    ]
    with conn.cursor() as cur:
        for asset in assets:
            cur.execute(
                """
                INSERT INTO assets (symbol, name, coingecko_id, csv_path, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO NOTHING
                """,
                (
                    asset["symbol"],
                    asset["name"],
                    asset["coingecko_id"],
                    asset["csv_path"],
                    True,
                    utc_now(),
                ),
            )


def _seed_users(conn):
    defaults = [
        ("admin", "System Admin", "admin@cryptopredict.local", current_app.config["DEFAULT_ADMIN_PASSWORD"], "admin"),
        (
            "scientist",
            "Data Scientist",
            "scientist@cryptopredict.local",
            current_app.config["DEFAULT_SCIENTIST_PASSWORD"],
            "scientist",
        ),
        ("investor", "End User", "investor@cryptopredict.local", current_app.config["DEFAULT_USER_PASSWORD"], "user"),
    ]
    now = utc_now()
    with conn.cursor() as cur:
        for username, full_name, email, password, role in defaults:
            cur.execute(
                """
                INSERT INTO users (username, full_name, email, password_hash, role, created_at, updated_at, last_login_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
                """,
                (
                    username,
                    full_name,
                    email,
                    generate_password_hash(password),
                    role,
                    now,
                    now,
                    None,
                ),
            )


def _seed_price_history(conn, root_path):
    with conn.cursor() as cur:
        cur.execute("SELECT symbol, csv_path FROM assets")
        assets = cur.fetchall()

    with conn.cursor() as cur:
        for asset in assets:
            csv_path = Path(asset["csv_path"] or "")
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                cur.execute(
                    """
                    INSERT INTO price_history (
                        asset_symbol, trade_date, open, high, low, close, adj_close, volume, source, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (asset_symbol, trade_date) DO NOTHING
                    """,
                    (
                        asset["symbol"],
                        str(row["Date"]),
                        float(row["Open"]),
                        float(row["High"]),
                        float(row["Low"]),
                        float(row["Close"]),
                        float(row["Adj Close"]),
                        float(row["Volume"]),
                        "seed_csv",
                        utc_now(),
                    ),
                )


def _seed_news(conn):
    items = [
        (
            "Bitcoin liquidity remains a key macro watchpoint",
            "Market watchers continue tracking how liquidity conditions shape near-term crypto demand.",
            "https://www.coindesk.com/markets/bitcoin-liquidity-watchpoint/",
        ),
        (
            "Ethereum network activity stays central to investor sentiment",
            "On-chain participation and ETF-related narratives remain the main ETH catalysts.",
            "https://www.coindesk.com/markets/ethereum-network-activity-sentiment/",
        ),
        (
            "Risk management remains the core theme for volatile crypto cycles",
            "Forecasting tools are most useful when paired with disciplined position sizing and scenario analysis.",
            "https://www.coindesk.com/markets/crypto-risk-management-cycles/",
        ),
    ]
    with conn.cursor() as cur:
        for title, summary, url in items:
            cur.execute(
                """
                INSERT INTO market_news (title, summary, url, source, published_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                """,
                (
                    title,
                    summary,
                    url,
                    "CoinDesk",
                    utc_now(),
                    utc_now(),
                ),
            )


def init_db(app):
    with app.app_context():
        try:
            with _connect() as conn:
                _apply_schema(conn)
                seed_database(app.root_path, conn)
        except OperationalError as exc:
            raise RuntimeError(
                "PostgreSQL connection failed. Set DATABASE_URL to a valid PostgreSQL DSN before starting the app."
            ) from exc


def seed_database(root_path, conn=None):
    close_after = conn is None
    conn = conn or _connect()
    try:
        if _table_count(conn, "users") == 0:
            _seed_users(conn)
        if _table_count(conn, "assets") == 0:
            _seed_assets(conn, root_path)
        if _table_count(conn, "price_history") == 0:
            _seed_price_history(conn, root_path)
        if _table_count(conn, "market_news") == 0:
            _seed_news(conn)
    finally:
        if close_after:
            conn.close()


def read_store():
    return deepcopy(DEFAULT_STORE)


def write_store(store):
    return store


def next_id(records):
    return max((item.get("id", 0) for item in records), default=0) + 1


def list_users():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM users ORDER BY id")
        return _normalize_rows(cur.fetchall())


def get_user(username, role=None):
    query = "SELECT * FROM users WHERE username = %s"
    params = [username]
    if role is not None:
        query += " AND role = %s"
        params.append(role)
    query += " LIMIT 1"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        return _normalize_row(cur.fetchone())


def update_user(username, **fields):
    allowed = {"full_name", "email", "password_hash", "role", "last_login_at"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_user(username)

    assignments = [sql.SQL("{} = %s").format(sql.Identifier(key)) for key in updates]
    assignments.append(sql.SQL("updated_at = %s"))
    values = list(updates.values()) + [utc_now(), username]
    query = sql.SQL("UPDATE users SET {} WHERE username = %s RETURNING *").format(sql.SQL(", ").join(assignments))
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(query, values)
        return _normalize_row(cur.fetchone())


def delete_user(username):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE username = %s", (username,))
        return cur.rowcount > 0


def list_assets():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM assets WHERE is_active = TRUE ORDER BY symbol")
        return _normalize_rows(cur.fetchall())


def get_asset(symbol):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM assets WHERE symbol = %s AND is_active = TRUE LIMIT 1", (symbol.upper(),))
        return _normalize_row(cur.fetchone())


def list_price_history(symbol, limit=None):
    query = """
        SELECT id, asset_symbol, trade_date, open, high, low, close, adj_close, volume, source, created_at
        FROM price_history
        WHERE asset_symbol = %s
        ORDER BY trade_date
    """
    params = [symbol.upper()]
    if limit:
        query = """
            SELECT *
            FROM (
                SELECT id, asset_symbol, trade_date, open, high, low, close, adj_close, volume, source, created_at
                FROM price_history
                WHERE asset_symbol = %s
                ORDER BY trade_date DESC
                LIMIT %s
            ) AS recent_rows
            ORDER BY trade_date
        """
        params.append(limit)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        return _normalize_rows(cur.fetchall())


def upsert_price_rows(symbol, rows, source="api"):
    symbol = symbol.upper()
    with _connect() as conn, conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO price_history (
                    asset_symbol, trade_date, open, high, low, close, adj_close, volume, source, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (asset_symbol, trade_date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    adj_close = EXCLUDED.adj_close,
                    volume = EXCLUDED.volume,
                    source = EXCLUDED.source,
                    created_at = EXCLUDED.created_at
                """,
                (
                    symbol,
                    row["trade_date"],
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["adj_close"]),
                    float(row["volume"]),
                    source,
                    utc_now(),
                ),
            )


def list_news(limit=3):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, summary, url, source, published_at, created_at
            FROM market_news
            ORDER BY published_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return _normalize_rows(cur.fetchall())


def upsert_news_items(items):
    with _connect() as conn, conn.cursor() as cur:
        for item in items:
            cur.execute(
                """
                INSERT INTO market_news (title, summary, url, source, published_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    source = EXCLUDED.source,
                    published_at = EXCLUDED.published_at
                """,
                (
                    item["title"],
                    item["summary"],
                    item["url"],
                    item["source"],
                    item["published_at"],
                    utc_now(),
                ),
            )
    return items


def get_sync_state(key):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM sync_state WHERE key = %s LIMIT 1", (key,))
        row = cur.fetchone()
        return row["value"] if row else None


def set_sync_state(key, value):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sync_state (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )


def add_model_registry(record):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO model_registry (
                asset_symbol, model_name, version, horizon_days, trained_at, rmse, mae, r2,
                params_json, feature_importances_json, model_path, dataset_source, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                record["asset_symbol"],
                record["model_name"],
                record["version"],
                record["horizon_days"],
                record["trained_at"],
                record["rmse"],
                record["mae"],
                record["r2"],
                record["params_json"],
                record["feature_importances_json"],
                record["model_path"],
                record["dataset_source"],
                record["is_active"],
            ),
        )
        return _normalize_row(cur.fetchone())


def deactivate_models(symbol, model_name, horizon_days):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE model_registry
            SET is_active = FALSE
            WHERE asset_symbol = %s AND model_name = %s AND horizon_days = %s
            """,
            (symbol.upper(), model_name, horizon_days),
        )


def get_active_model_record(symbol, model_name, horizon_days):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM model_registry
            WHERE asset_symbol = %s
              AND model_name = %s
              AND horizon_days = %s
              AND is_active = TRUE
            ORDER BY trained_at DESC
            LIMIT 1
            """,
            (symbol.upper(), model_name, horizon_days),
        )
        return _normalize_row(cur.fetchone())


def list_model_registry(symbol=None, limit=10):
    query = "SELECT * FROM model_registry"
    params = []
    if symbol:
        query += " WHERE asset_symbol = %s"
        params.append(symbol.upper())
    query += " ORDER BY trained_at DESC LIMIT %s"
    params.append(limit)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        return _normalize_rows(cur.fetchall())


def latest_metrics(symbol):
    output = {}
    for row in list_model_registry(symbol=symbol, limit=50):
        if row["is_active"] and row["model_name"] not in output:
            output[row["model_name"]] = row
    return output


def add_prediction(record):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO prediction_logs (
                user_id, asset_symbol, horizon_days, model_choice, current_price,
                dt_prediction, rf_prediction, created_at, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                record["user_id"],
                record["asset_symbol"],
                record["horizon_days"],
                record["model_choice"],
                record["current_price"],
                record.get("dt_prediction"),
                record.get("rf_prediction"),
                record["created_at"],
                record["status"],
            ),
        )
        return _normalize_row(cur.fetchone())


def list_prediction_logs():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM prediction_logs ORDER BY created_at DESC")
        return _normalize_rows(cur.fetchall())


def prediction_traffic(limit=7):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT created_at::date AS day, COUNT(*) AS total
            FROM prediction_logs
            GROUP BY created_at::date
            ORDER BY day DESC
            LIMIT %s
            """,
            (limit,),
        )
        return _normalize_rows(cur.fetchall())


def prediction_distribution():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT asset_symbol, COUNT(*) AS total
            FROM prediction_logs
            GROUP BY asset_symbol
            ORDER BY asset_symbol
            """
        )
        return _normalize_rows(cur.fetchall())


def add_feedback(prediction_log_id, username, message):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO feedback_reports (prediction_log_id, username, message, created_at, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (prediction_log_id, username, message, utc_now(), "open"),
        )
        return _normalize_row(cur.fetchone())


def list_feedback_reports(status=None, limit=None):
    query = "SELECT * FROM feedback_reports"
    params = []
    if status is not None:
        query += " WHERE status = %s"
        params.append(status)
    query += " ORDER BY created_at DESC"
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        return _normalize_rows(cur.fetchall())


def add_notification(target_role, title, message, level="info"):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notifications (target_role, title, message, level, is_read, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (target_role, title, message, level, False, utc_now()),
        )
        return _normalize_row(cur.fetchone())


def list_notifications(target_role, limit=5):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM notifications
            WHERE target_role = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (target_role, limit),
        )
        return _normalize_rows(cur.fetchall())


def unread_notification_count(target_role):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE target_role = %s AND is_read = FALSE
            """,
            (target_role,),
        )
        return cur.fetchone()["total"]


def mark_notifications_read(target_role):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notifications
            SET is_read = TRUE
            WHERE target_role = %s AND is_read = FALSE
            """,
            (target_role,),
        )
        return cur.rowcount > 0


def add_audit(actor_username, actor_role, event_type, description, status="success"):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_logs (actor_username, actor_role, event_type, description, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (actor_username, actor_role, event_type, description, status, utc_now()),
        )
        return _normalize_row(cur.fetchone())


def list_audit_logs(limit=8):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return _normalize_rows(cur.fetchall())
