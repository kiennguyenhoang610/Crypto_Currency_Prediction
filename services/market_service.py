import json
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from database import (
    get_asset,
    get_sync_state,
    list_assets,
    list_news,
    list_price_history,
    set_sync_state,
    upsert_news_items,
    upsert_price_rows,
    utc_now,
)


class MarketService:
    def __init__(self, config):
        self.config = config
        self.ssl_context = ssl.create_default_context()

    def list_assets(self):
        return list_assets()

    def get_asset(self, symbol):
        return get_asset(symbol)

    def get_price_series(self, symbol, limit=90):
        return list_price_history(symbol, limit=limit)

    def get_latest_news(self, limit=3):
        return list_news(limit=limit)

    def sync_all(self, symbol=None):
        self.sync_news_from_feed(limit=6)
        if symbol:
            self.sync_market_data(symbol)
            return
        for asset in self.list_assets():
            self.sync_market_data(asset["symbol"])

    def sync_news_from_feed(self, limit=6):
        now = datetime.now(timezone.utc)
        sync_key = "news_feed"
        last_sync = get_sync_state(sync_key)
        if last_sync:
            last_sync_dt = datetime.fromisoformat(last_sync)
            if now - last_sync_dt < timedelta(minutes=30):
                return self.get_latest_news(limit)

        feed_url = self.config.get("NEWS_FEED_URL")
        if not feed_url:
            return self.get_latest_news(limit)

        request = urllib.request.Request(feed_url, headers={"User-Agent": "CryptoPredict/1.0"})
        with urllib.request.urlopen(request, timeout=8, context=self.ssl_context) as response:
            raw_xml = response.read()

        root = ET.fromstring(raw_xml)
        channel = root.find("channel")
        if channel is None:
            return self.get_latest_news(limit)

        items = []
        for node in channel.findall("item")[:limit]:
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            description = (node.findtext("description") or "").strip()
            published = self._normalize_feed_datetime((node.findtext("pubDate") or utc_now()).strip())
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "summary": description[:320] if description else "No summary available.",
                    "url": link,
                    "source": "CoinDesk RSS",
                    "published_at": published,
                }
            )

        if items:
            upsert_news_items(items)
            set_sync_state(sync_key, utc_now())
        return self.get_latest_news(limit)

    def sync_market_data(self, symbol, days=30):
        asset = self.get_asset(symbol)
        if not asset or not asset.get("coingecko_id"):
            return self.get_price_series(symbol, limit=days)

        sync_key = f"market_{symbol.upper()}"
        last_sync = get_sync_state(sync_key)
        now = datetime.now(timezone.utc)
        if last_sync:
            last_sync_dt = datetime.fromisoformat(last_sync)
            if now - last_sync_dt < timedelta(hours=6):
                return self.get_price_series(symbol, limit=days)

        params = urllib.parse.urlencode(
            {
                "vs_currency": "usd",
                "days": str(days),
                "interval": "daily",
                "precision": "full",
            }
        )
        url = f"{self.config['COINGECKO_BASE_URL']}/coins/{asset['coingecko_id']}/market_chart?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "CryptoPredict/1.0"})
        with urllib.request.urlopen(request, timeout=8, context=self.ssl_context) as response:
            payload = json.loads(response.read().decode("utf-8"))

        prices = payload.get("prices", [])
        volumes = {self._date_key(item[0]): float(item[1]) for item in payload.get("total_volumes", [])}
        market_rows = []
        for timestamp_ms, price in prices:
            trade_date = self._date_key(timestamp_ms)
            close_value = float(price)
            market_rows.append(
                {
                    "trade_date": trade_date,
                    "open": close_value,
                    "high": close_value,
                    "low": close_value,
                    "close": close_value,
                    "adj_close": close_value,
                    "volume": volumes.get(trade_date, 0.0),
                }
            )

        if market_rows:
            upsert_price_rows(symbol, market_rows, source="coingecko_api")
            set_sync_state(sync_key, utc_now())
        return self.get_price_series(symbol, limit=days)

    def get_market_summary(self, symbol):
        series = self.get_price_series(symbol, limit=30)
        if not series:
            return None
        latest = series[-1]
        previous = series[-2] if len(series) > 1 else latest
        change = latest["close"] - previous["close"]
        change_pct = 0 if previous["close"] == 0 else (change / previous["close"]) * 100
        return {
            "latest_close": latest["close"],
            "latest_date": latest["trade_date"],
            "daily_change": change,
            "daily_change_pct": change_pct,
            "volume_avg_30d": sum(row["volume"] for row in series) / len(series),
            "high_30d": max(row["high"] for row in series),
            "low_30d": min(row["low"] for row in series),
            "source": latest.get("source", "json_store"),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }

    def upsert_price_rows(self, symbol, rows, source="api"):
        upsert_price_rows(symbol, rows, source=source)

    def _date_key(self, timestamp_ms):
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()

    def _normalize_feed_datetime(self, value):
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except (TypeError, ValueError, IndexError):
            return utc_now()
