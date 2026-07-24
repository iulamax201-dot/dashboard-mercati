"""
Scarica prezzi, fondamentali (target analisti, P/E, ...) e notizie recenti per
i titoli del Nasdaq-100 e scrive docs/stocks.json.

Robusto: retry, pause anti rate-limit, tolleranza ai fallimenti (salta il
singolo titolo senza interrompere tutto). Eseguito da GitHub Actions.

Uso:
    python scripts/fetch_stocks.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from typing import Dict, List, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_analysis  # noqa: E402
from nasdaq100 import NASDAQ_100  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "stocks.json")

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}
SESSION = requests.Session()
SESSION.headers.update(UA)

RECO_MAP = {
    "strong_buy": "strong_buy", "buy": "buy", "hold": "hold",
    "underperform": "sell", "sell": "sell", "strong_sell": "strong_sell",
    "none": None,
}


def get_closes(symbol: str) -> Optional[List[float]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": "1y", "interval": "1d"}
    for attempt in range(3):
        try:
            r = SESSION.get(url, params=params, timeout=20)
            if r.status_code == 200:
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]["close"]
                closes = [float(c) for c in q if c is not None]
                if len(closes) > 60:
                    return closes
            elif r.status_code in (429, 999):
                time.sleep(2 * (attempt + 1))
        except Exception:  # noqa: BLE001
            time.sleep(1.2 * (attempt + 1))
    return None


def get_fundamentals(symbol: str) -> Dict:
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
    params = {"modules": "financialData,summaryDetail,price,defaultKeyStatistics"}
    for attempt in range(2):
        try:
            r = SESSION.get(url, params=params, timeout=20)
            if r.status_code != 200:
                time.sleep(1.5)
                continue
            res = r.json()["quoteSummary"]["result"][0]
            fd = res.get("financialData", {})
            sd = res.get("summaryDetail", {})

            def raw(d, k):
                v = d.get(k, {})
                return v.get("raw") if isinstance(v, dict) else None

            return {
                "target_mean": raw(fd, "targetMeanPrice"),
                "target_high": raw(fd, "targetHighPrice"),
                "target_low": raw(fd, "targetLowPrice"),
                "reco_key": RECO_MAP.get((fd.get("recommendationKey") or "none")),
                "reco_mean": raw(fd, "recommendationMean"),
                "num_analysts": raw(fd, "numberOfAnalystOpinions"),
                "pe": raw(sd, "trailingPE"),
                "div_yield": (raw(sd, "dividendYield") or 0) * 100
                if raw(sd, "dividendYield") else None,
                "market_cap": raw(res.get("price", {}), "marketCap"),
            }
        except Exception:  # noqa: BLE001
            time.sleep(1.2)
    return {}


def get_news(symbol: str, count: int = 2) -> List[Dict]:
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": symbol, "newsCount": count, "quotesCount": 0,
              "enableFuzzyQuery": "false"}
    try:
        r = SESSION.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return []
        items = r.json().get("news", [])[:count]
        out = []
        for it in items:
            ts = it.get("providerPublishTime")
            out.append({
                "title": it.get("title", "")[:160],
                "publisher": it.get("publisher", ""),
                "link": it.get("link", ""),
                "date": dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                if ts else None,
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def build() -> Dict:
    stocks: List[Dict] = []
    failed: List[str] = []
    total = len(NASDAQ_100)
    for i, (symbol, name) in enumerate(NASDAQ_100.items(), 1):
        closes = get_closes(symbol)
        if closes is None:
            failed.append(symbol)
            print(f"[{i}/{total}] {symbol}: prezzi non disponibili, salto")
            time.sleep(0.3)
            continue
        fund = get_fundamentals(symbol)
        news = get_news(symbol)
        stocks.append(stock_analysis.build_stock(symbol, name, closes, fund, news))
        print(f"[{i}/{total}] {symbol}: ok "
              f"(target={fund.get('target_mean')}, reco={fund.get('reco_key')})")
        time.sleep(0.35)  # anti rate-limit

    stocks.sort(key=lambda s: s.get("market_cap") or 0, reverse=True)
    if failed:
        print(f"Titoli falliti ({len(failed)}): {', '.join(failed)}")

    return {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "Yahoo Finance",
        "demo": False,
        "summary": stock_analysis.summary(stocks),
        "stocks": stocks,
    }


def main():
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    s = data["summary"]
    print(f"Scritto {OUT}: {s['count']} titoli "
          f"({s['buy']} compra / {s['hold']} mantieni / {s['sell']} vendi)")


if __name__ == "__main__":
    main()
