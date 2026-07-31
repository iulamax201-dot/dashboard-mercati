"""
Scarica i dati dei singoli titoli (lista curata) da Yahoo Finance, calcola
il verdetto tecnico e la stima di fair value e scrive docs/stocks.json per la
seconda pagina della dashboard (titoli.html).

Eseguito da GitHub Actions. In locale con rete limitata usare seed_stocks.py.

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
from yahoo_auth import make_session  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "stocks.json")

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}

SESSION, CRUMB = make_session()

# Lista curata: leader mondiali su tech/AI-semiconduttori, finanza/banche,
# salute/farma e lusso. Stile equilibrato (mix mega-cap, crescita, valore).
STOCKS = [
    {"name": "Nvidia", "ticker": "NVDA", "symbol": "NVDA", "theme": "Tech · AI / Semiconduttori"},
    {"name": "Microsoft", "ticker": "MSFT", "symbol": "MSFT", "theme": "Tech · AI / Cloud"},
    {"name": "Oracle", "ticker": "ORCL", "symbol": "ORCL", "theme": "Tech · AI / Cloud / Database"},
    {"name": "Apple", "ticker": "AAPL", "symbol": "AAPL", "theme": "Tech · Consumer tech"},
    {"name": "ASML", "ticker": "ASML", "symbol": "ASML", "theme": "Tech · Semiconduttori"},
    {"name": "SK Hynix", "ticker": "000660.KS", "symbol": "000660.KS", "theme": "Tech · AI / Semiconduttori (memorie)"},
    {"name": "JPMorgan", "ticker": "JPM", "symbol": "JPM", "theme": "Finanza · Banche"},
    {"name": "Intesa Sanpaolo", "ticker": "ISP.MI", "symbol": "ISP.MI", "theme": "Finanza · Banche (Italia)"},
    {"name": "Eli Lilly", "ticker": "LLY", "symbol": "LLY", "theme": "Salute · Farmaceutica"},
    {"name": "Novo Nordisk", "ticker": "NVO", "symbol": "NVO", "theme": "Salute · Farmaceutica"},
    {"name": "LVMH", "ticker": "MC.PA", "symbol": "MC.PA", "theme": "Lusso · Beni voluttuari"},
    {"name": "Ferrari", "ticker": "RACE", "symbol": "RACE", "theme": "Lusso · Auto (Italia)"},
]


def fetch_chart(symbol: str, rng: str = "2y", interval: str = "1d") -> Optional[Dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": rng, "interval": interval, "includePrePost": "false"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            if r.status_code == 200:
                res = r.json()["chart"]["result"][0]
                ts = res["timestamp"]
                q = res["indicators"]["quote"][0]
                meta = res.get("meta", {})
                dates, o, h, l, c, v = [], [], [], [], [], []
                for i, t in enumerate(ts):
                    if None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]):
                        continue
                    dates.append(dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"))
                    o.append(float(q["open"][i]))
                    h.append(float(q["high"][i]))
                    l.append(float(q["low"][i]))
                    c.append(float(q["close"][i]))
                    v.append(float(q["volume"][i] or 0))
                if len(c) > 60:
                    return {"dates": dates, "open": o, "high": h, "low": l,
                            "close": c, "volume": v,
                            "currency": meta.get("currency", "USD"),
                            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName", "")}
        except Exception as e:  # noqa: BLE001
            print(f"  Chart tentativo {attempt+1} fallito per {symbol}: {e}")
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_fundamentals(symbol: str) -> Dict:
    """P/E, target analisti e rating dal titolo (Yahoo quoteSummary)."""
    modules = "summaryDetail,defaultKeyStatistics,financialData,price"
    r = None
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        params = {"modules": modules}
        if CRUMB:
            params["crumb"] = CRUMB
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                r = resp
                break
        except Exception:  # noqa: BLE001
            continue
    if r is None:
        return {}
    try:
        res = r.json()["quoteSummary"]["result"][0]
    except Exception as e:  # noqa: BLE001
        print(f"  Fondamentali {symbol} non disponibili: {e}")
        return {}
    sd = res.get("summaryDetail", {})
    ks = res.get("defaultKeyStatistics", {})
    fd = res.get("financialData", {})
    pr = res.get("price", {})

    def raw(d, k):
        v = d.get(k, {})
        return v.get("raw") if isinstance(v, dict) else None

    def txt(d, k):
        v = d.get(k, {})
        if isinstance(v, dict):
            return v.get("raw") if "raw" in v else v.get("fmt")
        return v

    out = {
        "pe": raw(sd, "trailingPE"),
        "forward_pe": raw(sd, "forwardPE") or raw(ks, "forwardPE"),
        "target_mean": raw(fd, "targetMeanPrice"),
        "target_low": raw(fd, "targetLowPrice"),
        "target_high": raw(fd, "targetHighPrice"),
        "rating": txt(fd, "recommendationKey"),
        "n_analysts": raw(fd, "numberOfAnalystOpinions"),
        "currency": pr.get("currency"),
        "exchange": pr.get("exchangeName"),
    }
    return {k: (round(v, 2) if isinstance(v, float) else v)
            for k, v in out.items() if v is not None}


def build() -> Dict:
    stocks_out: List[Dict] = []
    for spec in STOCKS:
        print(f"Scarico {spec['name']} ({spec['symbol']})...")
        chart = fetch_chart(spec["symbol"])
        if chart is None:
            print(f"  {spec['name']}: dati non disponibili, salto")
            continue
        fund = fetch_fundamentals(spec["symbol"])
        currency = fund.get("currency") or chart.get("currency") or "USD"
        market = chart.get("exchange") or fund.get("exchange") or ""
        stocks_out.append(stock_analysis.build_stock(
            spec["name"], spec["ticker"], currency, market, spec["theme"],
            chart["dates"], chart["open"], chart["high"], chart["low"],
            chart["close"], chart["volume"], fundamentals=fund,
        ))
        time.sleep(0.5)

    if not stocks_out:
        raise RuntimeError("Nessun titolo scaricato")

    # ordina per forza tecnica (i più interessanti in alto)
    stocks_out.sort(key=lambda s: s["score"], reverse=True)

    bull = sum(1 for s in stocks_out if s["verdict"] == "Bullish")
    bear = sum(1 for s in stocks_out if s["verdict"] == "Bearish")
    return {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "Yahoo Finance",
        "demo": False,
        "count": len(stocks_out),
        "bullish_count": bull,
        "bearish_count": bear,
        "stocks": stocks_out,
    }


def main():
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Scritto {OUT} — {data['count']} titoli "
          f"({data['bullish_count']} bullish, {data['bearish_count']} bearish)")


if __name__ == "__main__":
    main()
