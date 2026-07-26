"""
Genera un docs/data.json DIMOSTRATIVO senza accesso a internet, così che la
dashboard mostri qualcosa al primo caricamento (prima che GitHub Actions
esegua il primo aggiornamento reale).

I dati sono sintetici e chiaramente marcati come "demo". Verranno sostituiti
da dati reali al primo run del workflow.

Uso:
    python scripts/seed_data.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data.json")

# valori di partenza realistici (livelli approssimativi degli indici)
SEEDS = [
    {"name": "S&P 500", "symbol": "^GSPC", "start": 4800, "drift": 0.00035, "vol": 0.009, "etf": "SPY"},
    {"name": "Dow Jones", "symbol": "^DJI", "start": 38000, "drift": 0.00025, "vol": 0.008, "etf": "DIA"},
    {"name": "Nasdaq", "symbol": "^IXIC", "start": 15200, "drift": 0.00045, "vol": 0.012, "etf": "QQQ"},
]


def gen_series(spec: Dict, n: int = 320, seed: int = 0):
    rng = random.Random(seed)
    price = spec["start"]
    dates, o, h, l, c, v = [], [], [], [], [], []
    today = dt.date.today()
    # genera all'indietro per avere date di trading (salta i weekend)
    day = today - dt.timedelta(days=int(n * 1.45))
    count = 0
    while count < n:
        if day.weekday() < 5:  # lun-ven
            shock = rng.gauss(spec["drift"], spec["vol"])
            # leggera stagionalità/ondulazione per un grafico credibile
            wave = 0.0006 * math.sin(count / 18.0)
            open_p = price
            price = price * (1 + shock + wave)
            high_p = max(open_p, price) * (1 + abs(rng.gauss(0, 0.003)))
            low_p = min(open_p, price) * (1 - abs(rng.gauss(0, 0.003)))
            dates.append(day.strftime("%Y-%m-%d"))
            o.append(open_p); h.append(high_p); l.append(low_p); c.append(price)
            v.append(rng.uniform(2.5e9, 5e9))
            count += 1
        day += dt.timedelta(days=1)
    return dates, o, h, l, c, v


def main():
    indices_out: List[Dict] = []
    for i, spec in enumerate(SEEDS):
        dates, o, h, l, c, v = gen_series(spec, seed=i + 7)
        fund = {
            "proxy_etf": spec["etf"],
            "pe": round(random.uniform(19, 29), 2),
            "yield": round(random.uniform(0.5, 2.0), 2),
            "beta": 1.0,
            "note": "valori dimostrativi",
        }
        ath = max(c) * random.uniform(1.0, 1.08)  # record poco sopra
        news = [
            {"title": f"{spec['name']}: sintesi dimostrativa dei mercati",
             "publisher": "Demo", "link": "",
             "date": dt.date.today().isoformat() + " 09:00"},
            {"title": "Fattori macro e trimestrali in focus (esempio)",
             "publisher": "Demo", "link": "",
             "date": dt.date.today().isoformat() + " 08:30"},
        ]
        indices_out.append(
            analysis.build_index_analysis(
                spec["name"], spec["symbol"], dates, o, h, l, c, v,
                fundamentals=fund, ath=ath, news=news,
            )
        )

    # settori demo per la rotazione
    demo_sectors = []
    groups = [("XLK","Tecnologia","Ciclico"),("XLC","Comunicazioni","Ciclico"),
              ("XLY","Consumi discrezionali","Ciclico"),("XLF","Finanziari","Ciclico"),
              ("XLI","Industriali","Ciclico"),("XLB","Materiali","Ciclico"),
              ("XLE","Energia","Ciclico"),("XLV","Sanità","Difensivo"),
              ("XLP","Beni di prima necessità","Difensivo"),("XLU","Utilities","Difensivo"),
              ("XLRE","Immobiliare","Difensivo")]
    for sym,nm,grp in groups:
        r1=round(random.uniform(-6,8),1); r3=round(random.uniform(-10,15),1)
        demo_sectors.append({"symbol":sym,"name":nm,"group":grp,"ret_1m":r1,
            "ret_3m":r3,"rsi":round(random.uniform(35,68),0),
            "above_sma50":random.random()>0.4,"score":round(r1*0.5+r3*0.5,2)})
    rotation = analysis.build_rotation(demo_sectors)

    market = analysis.market_summary(indices_out)
    market["news_market"] = [
        {"title":"Mercati: sintesi dimostrativa (macro e trimestrali)","publisher":"Il Sole 24 Ore","link":"","date":dt.date.today().isoformat()+" 09:00"},
        {"title":"Wall Street ed Europa: focus tassi e utili (esempio)","publisher":"Milano Finanza","link":"","date":dt.date.today().isoformat()+" 08:30"},
    ]
    market["news_research"] = [
        {"title":"Outlook di mercato — nota dimostrativa","publisher":"Goldman Sachs","link":"","date":dt.date.today().isoformat()},
        {"title":"Guide to the Markets — aggiornamento (esempio)","publisher":"J.P. Morgan","link":"","date":dt.date.today().isoformat()},
    ]
    market["research_links"] = [
        {"name":"Goldman Sachs — Insights","url":"https://www.goldmansachs.com/insights"},
        {"name":"J.P. Morgan — Guide to the Markets","url":"https://am.jpmorgan.com/it/it/asset-management/adv/insights/market-insights/guide-to-the-markets/"},
        {"name":"Fidelity — Settori e mercati","url":"https://www.fidelity.com/sector-investing/overview"},
        {"name":"Il Sole 24 Ore — Finanza","url":"https://www.ilsole24ore.com/sez/finanza"},
        {"name":"Milano Finanza","url":"https://www.milanofinanza.it/"},
        {"name":"Investing.com Italia","url":"https://it.investing.com/"},
    ]

    # futures demo
    futures = []
    for sym,nm,base in [("ES=F","S&P 500 · futures",5900),("YM=F","Dow Jones · futures",37300),("NQ=F","Nasdaq 100 · futures",20600)]:
        chg=round(random.uniform(-1.2,1.2),2)
        spark=[round(base*(1+random.uniform(-0.02,0.02)),2) for _ in range(40)]
        futures.append({"symbol":sym,"name":nm,"price":round(base*(1+chg/100),2),
            "change_pct":chg,"as_of":dt.date.today().isoformat(),"sparkline":spark})

    data = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "Dati dimostrativi (sintetici)",
        "demo": True,
        "market": market,
        "indices": indices_out,
        "rotation": rotation,
        "futures": futures,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Scritto seed demo in {OUT} — fase: {data['market']['phase']}")


if __name__ == "__main__":
    main()
