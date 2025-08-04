#!/usr/bin/env python3
"""
Back-fill Hyperliquid funding-rate history for the past N days
(default 7) and push to InfluxDB.  Run once, then rely on the
real-time collector for new data.
"""

import argparse
import os
import sys
import logging
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import WritePrecision, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
import pandas as pd


# ---------- configuration ----------
load_dotenv(override=True)
NEEDED = ("INFLUXDB_URL", "INFLUXDB_TOKEN", "INFLUXDB_ORG", "INFLUXDB_BUCKET")
miss = [k for k in NEEDED if not os.getenv(k)]
if miss:
    sys.stderr.write(f"[fatal] missing env vars: {', '.join(miss)}\n")
    sys.exit(1)

URL, TOKEN, ORG, BUCKET = (
    os.getenv("INFLUXDB_URL"),
    os.getenv("INFLUXDB_TOKEN"),
    os.getenv("INFLUXDB_ORG"),
    os.getenv("INFLUXDB_BUCKET"),
)

SYMBOLS = ["BERA","BTC","ETH","FARTCOIN","HYPE","PENGU","PUMP","PURR","SOL", ]

parser = argparse.ArgumentParser(
    description="Hyperliquid funding-rate back-filler")
parser.add_argument("--days", type=int, default=7,
                    help="Days to look back (default 7)")
args = parser.parse_args()
SINCE = datetime.now(timezone.utc) - timedelta(days=args.days)

# ---------- HTTP with retry ----------
sess = requests.Session()
sess.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset(["POST"]),
        ),
    ),
)

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------- Influx ----------
client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)

# 建立 write_api 時直接指定同步模式
write_api = client.write_api(write_options=SYNCHRONOUS)


def fetch_history(symbol: str):
    """Return list of {'ts': int(ms), 'rate': float} for <symbol>."""
    payload = {
        "type": "fundingHistory",
        "coin": symbol,
        "startTime": int(SINCE.timestamp() * 1000),
        "endTime": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    try:
        r = sess.post("https://api.hyperliquid.xyz/info", json=payload, timeout=10)
        r.raise_for_status()
    except requests.HTTPError as e:
        logging.warning("HTTP %s for %s – skipped", e.response.status_code, symbol)
        return []
    data = r.json()               # [{'coin':'BTC','fundingRate':'…','time':1683…}, …]
    return [
        {"ts": int(d["time"]), "rate": float(d["fundingRate"])}
        for d in data
        if datetime.fromtimestamp(d["time"] / 1000, tz=timezone.utc) >= SINCE
    ]


def main():
    total = 0
    for sym in SYMBOLS:
        logging.info("fetching %s …", sym)
        rows = fetch_history(sym)
        if not rows:
            logging.warning("no data for %s in last %d days", sym, args.days)
            continue

        points = [
            {
                "measurement": "funding_rate",
                "tags": {"exchange": "hyperliquid", "symbol": sym},
                "fields": {
                    "rate": r["rate"],
                    "apr": r["rate"] * 24 * 365,
                },
                "time": pd.to_datetime(r["ts"], unit='ms').floor('s'),        # ms; precision set per-write
            }
            for r in rows
        ]
        print(points[:3])
        write_api.write(bucket=BUCKET, record=points,
                        write_precision=WritePrecision.MS)
        logging.info("wrote %d points for %s", len(points), sym)
        total += len(points)

    logging.info("backfill complete – %d total points", total)


if __name__ == "__main__":
    main()
