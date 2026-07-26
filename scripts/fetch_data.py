"""
Scarica i dati di S&P 500, Dow Jones e Nasdaq da Yahoo Finance (endpoint
pubblici, senza chiave API), calcola indicatori e analisi e scrive
docs/data.json.

Eseguito da GitHub Actions (che ha internet pieno). In locale, in ambienti
con rete limitata, usare `seed_data.py` per generare dati dimostrativi.

Uso:
    python scripts/fetch_data.py            # scrive docs/data.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data.json")

from yahoo_auth import make_session  # noqa: E402

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}

# sessione autenticata (cookie + crumb) per i fondamentali
SESSION, CRUMB = make_session()

# Indici e ETF proxy per i fondamentali (gli indici non hanno P/E diretto).
INDICES = [
    {"name": "S&P 500", "symbol": "^GSPC", "etf": "SPY", "stooq": "^spx"},
    {"name": "Dow Jones", "symbol": "^DJI", "etf": "DIA", "stooq": "^dji"},
    {"name": "Nasdaq", "symbol": "^IXIC", "etf": "QQQ", "stooq": "^ndq"},
]

# Indici europei (analisi compatta, solo Yahoo)
EUROPE = [
    {"name": "FTSE MIB", "symbol": "FTSEMIB.MI"},
    {"name": "DAX", "symbol": "^GDAXI"},
    {"name": "Euro Stoxx 50", "symbol": "^STOXX50E"},
]


def fetch_chart_yahoo(symbol: str, rng: str = "2y", interval: str = "1d") -> Optional[Dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": rng, "interval": interval, "includePrePost": "false"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            if r.status_code == 200:
                data = r.json()
                res = data["chart"]["result"][0]
                ts = res["timestamp"]
                q = res["indicators"]["quote"][0]
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
                            "close": c, "volume": v}
        except Exception as e:  # noqa: BLE001
            print(f"  Yahoo tentativo {attempt+1} fallito per {symbol}: {e}")
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_chart_stooq(stooq_symbol: str) -> Optional[Dict]:
    """Fallback: CSV giornaliero da Stooq."""
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code != 200 or "Date" not in r.text[:50]:
            return None
        lines = r.text.strip().splitlines()[1:]
        dates, o, h, l, c, v = [], [], [], [], [], []
        for ln in lines[-520:]:
            parts = ln.split(",")
            if len(parts) < 6:
                continue
            try:
                dates.append(parts[0])
                o.append(float(parts[1])); h.append(float(parts[2]))
                l.append(float(parts[3])); c.append(float(parts[4]))
                v.append(float(parts[5]) if parts[5] not in ("", "N/D") else 0.0)
            except ValueError:
                continue
        if len(c) > 60:
            return {"dates": dates, "open": o, "high": h, "low": l,
                    "close": c, "volume": v}
    except Exception as e:  # noqa: BLE001
        print(f"  Stooq fallito per {stooq_symbol}: {e}")
    return None


def fetch_fundamentals(etf: str) -> Dict:
    """P/E, yield e altri dati dall'ETF proxy tramite Yahoo quoteSummary."""
    modules = "summaryDetail,defaultKeyStatistics,price"
    r = None
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{etf}"
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
    try:
        if r is None:
            return {"proxy_etf": etf}
        res = r.json()["quoteSummary"]["result"][0]
        sd = res.get("summaryDetail", {})
        ks = res.get("defaultKeyStatistics", {})

        def raw(d, k):
            v = d.get(k, {})
            return v.get("raw") if isinstance(v, dict) else None

        out = {
            "proxy_etf": etf,
            "pe": raw(sd, "trailingPE"),
            "yield": (raw(sd, "yield") or 0) * 100 if raw(sd, "yield") is not None else None,
            "beta": raw(ks, "beta") or raw(sd, "beta"),
            "day_high": raw(sd, "dayHigh"),
            "day_low": raw(sd, "dayLow"),
        }
        return {k: (round(v, 2) if isinstance(v, float) else v)
                for k, v in out.items() if v is not None}
    except Exception as e:  # noqa: BLE001
        print(f"  Fondamentali {etf} non disponibili: {e}")
        return {"proxy_etf": etf}


def fetch_ath(symbol: str) -> Optional[float]:
    """Massimo storico (all-time high) da tutta la storia disponibile."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": "max", "interval": "1wk"}
    try:
        r = SESSION.get(url, params=params, timeout=25)
        if r.status_code != 200:
            return None
        res = r.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        highs = [h for h in (q.get("high") or []) if h is not None]
        closes = [c for c in (q.get("close") or []) if c is not None]
        vals = highs or closes
        # includi anche il massimo registrato nei metadati, se presente
        meta_hi = res.get("meta", {}).get("fiftyTwoWeekHigh")
        if vals:
            m = max(vals)
            return max(m, meta_hi) if meta_hi else m
    except Exception as e:  # noqa: BLE001
        print(f"  ATH {symbol} non disponibile: {e}")
    return None


# notizie per indice (query in italiano su Google News)
NEWS_QUERY = {
    "^GSPC": "S&P 500 borsa",
    "^DJI": "Dow Jones borsa",
    "^IXIC": "Nasdaq borsa",
}

# link permanenti agli hub di ricerca istituzionale (sempre disponibili)
RESEARCH_LINKS = [
    {"name": "Goldman Sachs — Insights", "url": "https://www.goldmansachs.com/insights"},
    {"name": "J.P. Morgan — Guide to the Markets",
     "url": "https://am.jpmorgan.com/it/it/asset-management/adv/insights/market-insights/guide-to-the-markets/"},
    {"name": "Fidelity — Settori e mercati",
     "url": "https://www.fidelity.com/sector-investing/overview"},
    {"name": "Il Sole 24 Ore — Finanza e Mercati",
     "url": "https://www.ilsole24ore.com/sez/finanza"},
    {"name": "Milano Finanza", "url": "https://www.milanofinanza.it/"},
    {"name": "Investing.com Italia", "url": "https://it.investing.com/"},
]


def _clean(txt: str) -> str:
    return " ".join((txt or "").split()).strip()


def fetch_google_news(query: str, count: int = 6) -> List[Dict]:
    """Notizie da Google News RSS (italiano). Aggrega Il Sole 24 Ore, Milano
    Finanza, Investing e articoli che riportano le view di GS/JPM/Fidelity."""
    url = ("https://news.google.com/rss/search?q=" + quote_plus(query) +
           "&hl=it&gl=IT&ceid=IT:it")
    try:
        r = SESSION.get(url, timeout=15)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        out = []
        for item in list(root.iter("item"))[:count]:
            title = _clean(item.findtext("title", ""))
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            src_el = item.find("{http://www.w3.org/2005/Atom}source")
            source = src_el.text if src_el is not None else None
            if source is None:
                source = item.findtext("source", "")
            # il titolo di Google News finisce spesso con " - Testata"
            if source is None and " - " in title:
                source = title.rsplit(" - ", 1)[-1]
            date = None
            if pub:
                try:
                    date = dt.datetime.strptime(
                        pub[:25], "%a, %d %b %Y %H:%M:%S").strftime("%Y-%m-%d %H:%M")
                except Exception:  # noqa: BLE001
                    date = pub[:16]
            out.append({
                "title": title[:200],
                "publisher": _clean(source or ""),
                "link": link,
                "date": date,
            })
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  Google News '{query}' non disponibile: {e}")
        return []


def fetch_news(symbol: str, count: int = 5) -> List[Dict]:
    """Notizie recenti collegate all'indice (Google News, italiano)."""
    q = NEWS_QUERY.get(symbol, symbol)
    news = fetch_google_news(q, count)
    if news:
        return news
    # fallback: Yahoo search
    try:
        r = SESSION.get("https://query1.finance.yahoo.com/v1/finance/search",
                        params={"q": symbol, "newsCount": count, "quotesCount": 0},
                        timeout=15)
        if r.status_code == 200:
            out = []
            for it in r.json().get("news", [])[:count]:
                ts = it.get("providerPublishTime")
                out.append({"title": it.get("title", "")[:200],
                            "publisher": it.get("publisher", ""),
                            "link": it.get("link", ""),
                            "date": dt.datetime.utcfromtimestamp(ts).strftime(
                                "%Y-%m-%d %H:%M") if ts else None})
            return out
    except Exception:  # noqa: BLE001
        pass
    return []


# 11 settori USA (SPDR) con classificazione ciclico/difensivo
SECTORS = [
    {"sym": "XLK", "name": "Tecnologia", "group": "Ciclico"},
    {"sym": "XLC", "name": "Comunicazioni", "group": "Ciclico"},
    {"sym": "XLY", "name": "Consumi discrezionali", "group": "Ciclico"},
    {"sym": "XLF", "name": "Finanziari", "group": "Ciclico"},
    {"sym": "XLI", "name": "Industriali", "group": "Ciclico"},
    {"sym": "XLB", "name": "Materiali", "group": "Ciclico"},
    {"sym": "XLE", "name": "Energia", "group": "Ciclico"},
    {"sym": "XLV", "name": "Sanità", "group": "Difensivo"},
    {"sym": "XLP", "name": "Beni di prima necessità", "group": "Difensivo"},
    {"sym": "XLU", "name": "Utilities", "group": "Difensivo"},
    {"sym": "XLRE", "name": "Immobiliare", "group": "Difensivo"},
]


def fetch_closes(symbol: str, rng: str = "6mo") -> Optional[List[float]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    try:
        r = SESSION.get(url, params={"range": rng, "interval": "1d"}, timeout=20)
        if r.status_code != 200:
            return None
        q = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [float(c) for c in q if c is not None]
        return closes if len(closes) > 30 else None
    except Exception:  # noqa: BLE001
        return None


def fetch_sectors() -> List[Dict]:
    out = []
    for sp in SECTORS:
        closes = fetch_closes(sp["sym"])
        if not closes:
            continue
        import indicators as ind
        price = closes[-1]
        r1 = ind.pct_return(closes, 21)
        r3 = ind.pct_return(closes, 63)
        rsi = ind.last_valid(ind.rsi(closes, 14))
        sma50 = ind.last_valid(ind.sma(closes, 50))
        score = ((r1 or 0) * 0.5 + (r3 or 0) * 0.5)
        out.append({
            "symbol": sp["sym"], "name": sp["name"], "group": sp["group"],
            "ret_1m": round(r1, 1) if r1 is not None else None,
            "ret_3m": round(r3, 1) if r3 is not None else None,
            "rsi": round(rsi, 0) if rsi is not None else None,
            "above_sma50": (price > sma50) if sma50 is not None else None,
            "score": round(score, 2),
        })
        time.sleep(0.25)
    return out


def fetch_europe() -> List[Dict]:
    """Analisi (compatta) degli indici europei principali."""
    out = []
    for spec in EUROPE:
        chart = fetch_chart_yahoo(spec["symbol"])
        if chart is None:
            print(f"  Europa: {spec['name']} non disponibile")
            continue
        ath = fetch_ath(spec["symbol"])
        out.append(analysis.build_index_analysis(
            spec["name"], spec["symbol"], chart["dates"], chart["open"],
            chart["high"], chart["low"], chart["close"], chart["volume"],
            fundamentals=None, ath=ath, news=[]))
        time.sleep(0.4)
    return out


def fetch_vix() -> Optional[Dict]:
    """Indice VIX (volatilità/paura) con livello, variazione e interpretazione."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
    try:
        r = SESSION.get(url, params={"range": "3mo", "interval": "1d"}, timeout=20)
        if r.status_code != 200:
            return None
        res = r.json()["chart"]["result"][0]
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) < 2:
            return None
        level = closes[-1]
        change = (level / closes[-2] - 1) * 100
        if level < 15:
            label, desc = "Calma", "Bassa volatilità attesa: mercato tranquillo (a volte compiacente)."
        elif level < 20:
            label, desc = "Normale", "Volatilità nella norma."
        elif level < 30:
            label, desc = "Nervosismo", "Tensione in aumento: gli investitori si coprono."
        else:
            label, desc = "Paura", "Stress elevato: forte avversione al rischio."
        return {"level": round(level, 2), "change_pct": round(change, 2),
                "label": label, "desc": desc,
                "sparkline": [round(c, 2) for c in closes[-40:]]}
    except Exception as e:  # noqa: BLE001
        print(f"  VIX non disponibile: {e}")
        return None


def build() -> Dict:
    indices_out: List[Dict] = []
    source = "Yahoo Finance"
    for spec in INDICES:
        print(f"Scarico {spec['name']} ({spec['symbol']})...")
        chart = fetch_chart_yahoo(spec["symbol"])
        if chart is None:
            print("  Yahoo non disponibile, provo Stooq...")
            chart = fetch_chart_stooq(spec["stooq"])
            if chart is not None:
                source = "Stooq (fallback)"
        if chart is None:
            raise RuntimeError(f"Impossibile scaricare dati per {spec['name']}")
        fund = fetch_fundamentals(spec["etf"])
        ath = fetch_ath(spec["symbol"])
        news = fetch_news(spec["symbol"])
        indices_out.append(
            analysis.build_index_analysis(
                spec["name"], spec["symbol"],
                chart["dates"], chart["open"], chart["high"],
                chart["low"], chart["close"], chart["volume"],
                fundamentals=fund, ath=ath, news=news,
            )
        )
        time.sleep(0.5)

    # notizie di mercato (italiane) e ricerca istituzionale (GS/JPM/Fidelity)
    market_news = fetch_google_news("borsa mercati Wall Street Europa", 7)
    research_news = fetch_google_news(
        '("Goldman Sachs" OR "JP Morgan" OR "J.P. Morgan" OR Fidelity) '
        '(mercati OR outlook OR previsioni OR settori OR azioni)', 7)

    # rotazione settoriale
    print("Scarico settori per la rotazione...")
    sectors = fetch_sectors()
    rotation = analysis.build_rotation(sectors)

    print("Scarico indici europei...")
    europe = fetch_europe()
    print("Scarico VIX...")
    vix = fetch_vix()

    market = analysis.market_summary(indices_out)
    market["news_market"] = market_news
    market["news_research"] = research_news
    market["research_links"] = RESEARCH_LINKS

    return {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source,
        "demo": False,
        "market": market,
        "indices": indices_out,
        "europe": europe,
        "vix": vix,
        "rotation": rotation,
    }


def main():
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Scritto {OUT} — fase mercato: {data['market']['phase']} "
          f"(fonte: {data['source']})")


if __name__ == "__main__":
    main()
