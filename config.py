import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
UPLOAD_DIR = BASE_DIR / "uploads"
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "crypto-predict-dev-secret")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:15432/crypto_predict",
    )
    LEGACY_JSON_PATH = os.environ.get("LEGACY_JSON_PATH", str(BASE_DIR / "crypto_predict_runtime.json"))
    DEFAULT_MARKET_SOURCE = os.environ.get("DEFAULT_MARKET_SOURCE", "local")
    COINGECKO_BASE_URL = os.environ.get(
        "COINGECKO_BASE_URL",
        "https://api.coingecko.com/api/v3",
    )
    NEWS_FEED_URL = os.environ.get(
        "NEWS_FEED_URL",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
    )
    MODEL_DIR = str(MODEL_DIR)
    UPLOAD_DIR = str(UPLOAD_DIR)
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin@123")
    DEFAULT_SCIENTIST_PASSWORD = os.environ.get(
        "DEFAULT_SCIENTIST_PASSWORD",
        "Scientist@123",
    )
    DEFAULT_USER_PASSWORD = os.environ.get("DEFAULT_USER_PASSWORD", "User@123")
