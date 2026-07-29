# Hyperliquid Funding Rate Dashboard

This project collects and visualizes funding rate data for Hyperliquid perpetual contracts. It periodically retrieves funding rates for each asset, converts them into annual percentage rates (APR), stores the data in InfluxDB, and displays it in a Grafana dashboard to help identify funding rate arbitrage opportunities worth further evaluation.

> This project provides monitoring and screening information only; it does not place orders automatically. Before executing an arbitrage strategy, you should evaluate spot/perpetual hedging, trading fees, slippage, borrowing costs, and liquidation risk.

## Features

- Fetches the latest Hyperliquid funding rates every hour
- Ranks assets by funding rate and the corresponding APR
- Backfills historical data for a configurable number of days (7 days by default)
- Writes time-series data to InfluxDB for Grafana queries and visualization
- Tracks funding rate changes by time range and individual asset
- Optionally sends real-time rankings to Telegram

By default, the application monitors `BERA`, `BTC`, `ETH`, `FARTCOIN`, `HYPE`, `PENGU`, `PUMP`, `PURR`, and `SOL`. You can customize this selection by editing the `SYMBOLS` list in the Python scripts.

## Architecture

```text
Hyperliquid API → Python collectors → InfluxDB → Grafana dashboard
                                  └→ Telegram (optional)
```

## Quick Start

Prerequisites: Python 3, Docker, and Docker Compose.

1. Create the local environment configuration:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set at least `INFLUXDB_TOKEN` and a strong `INFLUXDB_INIT_PASSWORD`. The `.env` file is ignored by Git; never commit real tokens or passwords.

2. Start InfluxDB and Grafana:

   ```bash
   docker compose -f decker-compose.yml up -d
   ```

3. Install the Python dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Backfill the last 7 days of data (adjustable with `--days`):

   ```bash
   python src/load_past_7days.py --days 7
   ```

5. Start the live collector, which runs hourly:

   ```bash
   python src/rank_fr_togua.py
   ```

Grafana is available at `http://localhost:3000` by default. After adding InfluxDB as a data source, you can create panels for funding rates, APR rankings, time ranges, and individual assets.

## Dashboard Screenshots

![Grafana home page](pic/homepage.png)

<img src="pic/dashboard.png" alt="Hyperliquid funding dashboard" width="600">

![Funding rate query results](pic/result.png)
