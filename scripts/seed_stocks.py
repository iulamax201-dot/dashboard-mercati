"""
Genera un docs/stocks.json DIMOSTRATIVO (offline) per far vedere subito la
sezione Nasdaq-100 in attesa del primo aggiornamento reale via GitHub Actions.

Uso:
    python scripts/seed_stocks.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_analysis  # noqa: E402
from nasdaq100 import NASDAQ_100  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "stocks.json")

RECOS = ["strong_buy", "buy", "buy", "hold", "hold", "sell"]


def gen_closes(rng: random.Random, n: int = 260):
    price = rng.uniform(40, 600)
    drift = rng.uniform(-0.0003, 0.0009)
    vol = rng.uniform(0.012, 0.03)
    out = []
    for i in range(n):
        price *= (1 + rng.gauss(drift, vol) + 0.0008 * math.sin(i / 15))
        out.append(max(1.0, price))
    return out


def main():
    stocks: List[dict] = []
    for i, (symbol, name) in enumerate(NASDAQ_100.items()):
        rng = random.Random(i * 7 + 13)
        closes = gen_closes(rng)
        price = closes[-1]
        fund = {
            "target_mean": round(price * rng.uniform(0.85, 1.25), 2),
            "reco_key": rng.choice(RECOS),
            "num_analysts": rng.randint(8, 45),
            "pe": round(rng.uniform(12, 55), 1),
            "div_yield": round(rng.uniform(0, 2.5), 2),
            "market_cap": rng.randint(20, 3200) * 1_000_000_000,
        }
        news = [{
            "title": f"{name}: aggiornamento dimostrativo di mercato",
            "publisher": "Demo", "link": "", "date": dt.date.today().isoformat(),
        }]
        stocks.append(stock_analysis.build_stock(symbol, name, closes, fund, news))

    stocks.sort(key=lambda s: s.get("market_cap") or 0, reverse=True)
    data = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "Dati dimostrativi (sintetici)",
        "demo": True,
        "summary": stock_analysis.summary(stocks),
        "stocks": stocks,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    s = data["summary"]
    print(f"Seed demo: {s['count']} titoli "
          f"({s['buy']} compra / {s['hold']} mantieni / {s['sell']} vendi)")


if __name__ == "__main__":
    main()
