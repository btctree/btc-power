"""Fetch full daily OHLCV history for BTCUSDT from Binance (spot).
Saves to ../data/btc_daily.csv. No look-ahead: each row is a closed daily candle.
"""
import requests, time, csv, datetime as dt, os

# data-api.binance.vision is the public market-data mirror (serves /api/v3/klines and,
# unlike api.binance.com, is reachable from US-based CI runners e.g. GitHub Actions).
BASE = os.environ.get("BINANCE_BASE", "https://data-api.binance.vision")
SYMBOL = "BTCUSDT"
INTERVAL = "1d"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "btc_daily.csv")

def fetch():
    start = int(dt.datetime(2017, 8, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    rows = []
    while True:
        r = requests.get(BASE + "/api/v3/klines", params={
            "symbol": SYMBOL, "interval": INTERVAL,
            "startTime": start, "limit": 1000}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        rows.extend(data)
        last_open = data[-1][0]
        if len(data) < 1000:
            break
        start = last_open + 86_400_000  # next day
        time.sleep(0.25)
    return rows

def main():
    raw = fetch()
    now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    out = []
    for k in raw:
        open_ms, o, h, l, c, v, close_ms = k[0], k[1], k[2], k[3], k[4], k[5], k[6]
        # only keep CLOSED candles (close time in the past) -> no partial today
        if close_ms > now_ms:
            continue
        d = dt.datetime.utcfromtimestamp(open_ms / 1000).strftime("%Y-%m-%d")
        out.append([d, float(o), float(h), float(l), float(c), float(v)])
    # de-dup by date (keep last)
    seen = {}
    for row in out:
        seen[row[0]] = row
    out = [seen[k] for k in sorted(seen)]
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        w.writerows(out)
    print(f"saved {len(out)} daily candles -> {OUT}")
    print(f"range: {out[0][0]} .. {out[-1][0]}")
    print(f"first close={out[0][4]}  last close={out[-1][4]}")

if __name__ == "__main__":
    main()
