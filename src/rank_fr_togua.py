#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid Funding → InfluxDB → Telegram（可選）
◆ 每小時整點執行，使用同步寫入確保不遺漏
"""

import os
import time
import logging
import requests
import schedule
from datetime import datetime, timezone
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError

# ───────────────────────────── 1. 讀取 .env ──────────────────────────────
load_dotenv()

# -- Telegram
TG_TOKEN = os.getenv("2nd_token")       # BotFather 產生的 token
TG_CHAT  = os.getenv("2nd_chat_id")     # 目標聊天室 id

# -- InfluxDB
INFLUX_URL    = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUXDB_TOKEN")
INFLUX_ORG    = os.getenv("INFLUXDB_ORG", "my-org")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "funding_rate")

# -- Hyperliquid
SYMBOLS = ["BERA", "BTC", "ETH", "FARTCOIN", "HYPE",
           "PENGU", "PUMP", "PURR", "SOL"]

API_URL = "https://api.hyperliquid.xyz/info"

# ───────────────────────────── 2. Logging ───────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ──────────────────────── 3. InfluxDB Client (同步) ──────────────────────
client    = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)  # 阻塞直至寫入成功

# ───────────────────── 4. 主要抓取與寫入邏輯 ────────────────────────────
def fetch_latest_rate(symbol: str) -> dict:
    """向 Hyperliquid 取 <symbol> 最新一筆 funding 資料（24h 內）"""
    now_ms   = int(time.time() * 1000)
    payload  = {"type": "fundingHistory",
                "coin": symbol,
                "startTime": now_ms - 86_400_000}
    try:
        resp = requests.post(API_URL, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json() or []
    except Exception as exc:
        logging.warning("%s API error: %s", symbol, exc)
        return {"coin": symbol, "fundingRate": 0, "time": now_ms}

    latest = max(data, key=lambda x: x["time"]) if data else {"coin": symbol,
                                                              "fundingRate": 0,
                                                              "time": now_ms}
    return latest


def build_points_and_message():
    """回傳 (InfluxDB Point 列表, Telegram 訊息字串)"""
    pts      = []
    snapshot = []  # (symbol, rate, apr)
    now_disp = datetime.now().strftime("%H:%M")

    for sym in SYMBOLS:
        rec  = fetch_latest_rate(sym)
        rate = float(rec["fundingRate"])
        apr  = rate * 24 * 365
        ts   = datetime.utcfromtimestamp(rec["time"] / 1000).replace(tzinfo=timezone.utc)

        pts.append(
            Point("funding_rate")
            .tag("exchange", "hyperliquid")
            .tag("symbol", sym)
            .field("rate", rate)
            .field("apr",  apr)
            .time(ts)                 # WritePrecision.MS 已由 Point 決定
        )
        snapshot.append((sym, rate, apr))

    # 排序組裝 Telegram 文字
    snapshot.sort(key=lambda x: x[1], reverse=True)
    emojis = [
        "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"
    ]

    lines   = [f"*🚀 Funding 排行 {now_disp}*"]
    for i, (sym, rate, apr) in enumerate(snapshot):
        lines.append(f"{emojis[i]} *{sym}* {rate:.4%} ({apr:.1%} APR)")
    return pts, "\n".join(lines)


def notify_telegram(text: str):
    """推送 Telegram，可自行註解停用"""
    if not TG_TOKEN or not TG_CHAT:
        return
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    body = {"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=body, timeout=10).raise_for_status()
    except Exception as exc:
        logging.warning("Telegram error: %s", exc)


def job():
    """抓取 → 寫入 Influx →（可選）Telegram"""
    try:
        points, message = build_points_and_message()
        if points:
            write_api.write(bucket=INFLUX_BUCKET, record=points)  # 同步寫入
            logging.info("Wrote %d points", len(points))
        # 若要推送，把下一行解除註解
        notify_telegram(message)
    except InfluxDBError as exc:
        logging.error("Influx write failed: %s", exc)


# ─────────────────────────── 5. Scheduler ───────────────────────────────
def main():
    job()  # 程式啟動先跑一次
    schedule.every().hour.at(":00").do(job)
    logging.info("Scheduler started – job will run every hour at :00 UTC")
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
