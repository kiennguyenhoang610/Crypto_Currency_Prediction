CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    last_login_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS assets (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    coingecko_id VARCHAR(120),
    csv_path TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    asset_symbol VARCHAR(10) NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    adj_close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    source VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_price_history_asset_date UNIQUE (asset_symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS market_news (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source VARCHAR(120) NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry (
    id BIGSERIAL PRIMARY KEY,
    asset_symbol VARCHAR(10) NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    model_name VARCHAR(20) NOT NULL,
    version VARCHAR(255) NOT NULL,
    horizon_days INTEGER NOT NULL,
    trained_at TIMESTAMPTZ NOT NULL,
    rmse DOUBLE PRECISION NOT NULL,
    mae DOUBLE PRECISION NOT NULL,
    r2 DOUBLE PRECISION NOT NULL,
    params_json TEXT NOT NULL,
    feature_importances_json TEXT NOT NULL,
    model_path TEXT NOT NULL,
    dataset_source VARCHAR(120) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_model_registry_lookup
ON model_registry (asset_symbol, model_name, horizon_days, is_active, trained_at DESC);

CREATE TABLE IF NOT EXISTS prediction_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_symbol VARCHAR(10) NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    horizon_days INTEGER NOT NULL,
    model_choice VARCHAR(20) NOT NULL,
    current_price DOUBLE PRECISION NOT NULL,
    dt_prediction DOUBLE PRECISION NULL,
    rf_prediction DOUBLE PRECISION NULL,
    created_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_reports (
    id BIGSERIAL PRIMARY KEY,
    prediction_log_id BIGINT NULL REFERENCES prediction_logs(id) ON DELETE SET NULL,
    username VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    target_role VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    level VARCHAR(30) NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor_username VARCHAR(100) NOT NULL,
    actor_role VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    key VARCHAR(120) PRIMARY KEY,
    value TEXT NOT NULL
);
