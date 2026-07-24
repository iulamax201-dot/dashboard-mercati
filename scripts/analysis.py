"""
Costruisce il payload di analisi per un singolo indice a partire dalle serie
OHLC. Calcola indicatori tecnici, un verdetto Bullish/Bearish/Neutrale con
punteggio motivato e un indicatore euristico di rischio correzione.

NB: il "rischio correzione" NON e' una previsione. E' una misura di quanto il
mercato appare tirato/ipercomprato in base a segnali statistici. I mercati
possono restare estesi a lungo. Solo scopo informativo, non consulenza.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import indicators as ind


def build_index_analysis(
    name: str,
    symbol: str,
    dates: List[str],
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    fundamentals: Optional[Dict] = None,
) -> Dict:
    sma50 = ind.sma(closes, 50)
    sma200 = ind.sma(closes, 200)
    sma20 = ind.sma(closes, 20)
    rsi14 = ind.rsi(closes, 14)
    macd_line, signal_line, hist = ind.macd(closes)
    bb_mid, bb_up, bb_low = ind.bollinger(closes, 20, 2.0)

    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    change = price - prev
    change_pct = (change / prev * 100) if prev else 0.0

    v_sma50 = ind.last_valid(sma50)
    v_sma200 = ind.last_valid(sma200)
    v_sma20 = ind.last_valid(sma20)
    v_rsi = ind.last_valid(rsi14)
    v_macd = ind.last_valid(macd_line)
    v_signal = ind.last_valid(signal_line)
    v_hist = ind.last_valid(hist)
    v_bb_up = ind.last_valid(bb_up)
    v_bb_low = ind.last_valid(bb_low)

    high_52 = max(closes[-252:]) if closes else price
    low_52 = min(closes[-252:]) if closes else price
    drawdown = ind.max_drawdown_from_high(closes[-252:])

    ret_1w = ind.pct_return(closes, 5)
    ret_1m = ind.pct_return(closes, 21)
    ret_3m = ind.pct_return(closes, 63)
    ret_6m = ind.pct_return(closes, 126)
    ret_1y = ind.pct_return(closes, 252)

    golden_cross = (
        v_sma50 is not None and v_sma200 is not None and v_sma50 > v_sma200
    )

    # ---------- VERDETTO (punteggio -> 0..100) ----------
    score = 50.0
    reasons: List[Dict] = []

    def add(cond: bool, weight: float, pos_txt: str, neg_txt: str):
        nonlocal score
        if cond:
            score += weight
            reasons.append({"sentiment": "bull", "text": pos_txt})
        else:
            score -= weight
            reasons.append({"sentiment": "bear", "text": neg_txt})

    if v_sma50 is not None:
        add(price > v_sma50, 8,
            "Prezzo sopra la media mobile a 50 giorni",
            "Prezzo sotto la media mobile a 50 giorni")
    if v_sma200 is not None:
        add(price > v_sma200, 12,
            "Prezzo sopra la media mobile a 200 giorni (trend di lungo positivo)",
            "Prezzo sotto la media mobile a 200 giorni (trend di lungo negativo)")
    if v_sma50 is not None and v_sma200 is not None:
        add(golden_cross, 10,
            "Golden cross: SMA50 sopra SMA200",
            "Death cross: SMA50 sotto SMA200")
    if v_hist is not None:
        add(v_hist > 0, 8,
            "MACD sopra la linea di segnale (momentum positivo)",
            "MACD sotto la linea di segnale (momentum negativo)")
    if ret_1m is not None:
        add(ret_1m > 0, 6,
            "Rendimento a 1 mese positivo",
            "Rendimento a 1 mese negativo")
    if v_rsi is not None:
        if v_rsi >= 70:
            score -= 4
            reasons.append({"sentiment": "warn",
                            "text": f"RSI ipercomprato ({v_rsi:.0f})"})
        elif v_rsi <= 30:
            score -= 2
            reasons.append({"sentiment": "warn",
                            "text": f"RSI ipervenduto ({v_rsi:.0f})"})
        elif 50 <= v_rsi < 70:
            score += 4
            reasons.append({"sentiment": "bull",
                            "text": f"RSI in zona di forza ({v_rsi:.0f})"})
        else:
            reasons.append({"sentiment": "neutral",
                            "text": f"RSI neutrale ({v_rsi:.0f})"})

    score = max(0.0, min(100.0, score))
    if score >= 62:
        verdict = "Bullish"
    elif score <= 42:
        verdict = "Bearish"
    else:
        verdict = "Neutrale"

    # ---------- RISCHIO CORREZIONE (0..100, euristico) ----------
    risk = 0.0
    risk_reasons: List[str] = []
    if v_rsi is not None and v_rsi > 70:
        risk += 30
        risk_reasons.append(f"RSI ipercomprato ({v_rsi:.0f})")
    elif v_rsi is not None and v_rsi > 65:
        risk += 15
        risk_reasons.append(f"RSI elevato ({v_rsi:.0f})")

    if v_sma200 is not None and v_sma200 > 0:
        stretch = (price / v_sma200 - 1) * 100
        if stretch > 12:
            risk += 25
            risk_reasons.append(f"Prezzo {stretch:.0f}% sopra la SMA200 (molto esteso)")
        elif stretch > 7:
            risk += 12
            risk_reasons.append(f"Prezzo {stretch:.0f}% sopra la SMA200 (esteso)")

    if v_bb_up is not None and price > v_bb_up:
        risk += 15
        risk_reasons.append("Prezzo oltre la banda di Bollinger superiore")

    # volatilita' recente (deviazione dei rendimenti giornalieri, 20g)
    vol = _recent_volatility(closes, 20)
    hist_vol = _recent_volatility(closes[:-20] or closes, 20)
    if vol is not None and hist_vol is not None and hist_vol > 0 and vol > hist_vol * 1.6:
        risk += 15
        risk_reasons.append("Volatilita' recente in aumento")

    if drawdown < -10:
        # gia' in correzione: il rischio di ulteriore ipercomprato scende
        risk = max(0.0, risk - 15)

    risk = max(0.0, min(100.0, risk))
    if risk >= 60:
        risk_label = "Alto"
    elif risk >= 30:
        risk_label = "Medio"
    else:
        risk_label = "Basso"
    if not risk_reasons:
        risk_reasons.append("Nessun segnale di eccesso rilevante al momento")

    # storico compatto per i grafici (max ~260 barre)
    hist_len = min(len(closes), 260)
    s = len(closes) - hist_len

    return {
        "name": name,
        "symbol": symbol,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "verdict": verdict,
        "score": round(score, 1),
        "reasons": reasons,
        "correction_risk": round(risk, 0),
        "correction_risk_label": risk_label,
        "correction_reasons": risk_reasons,
        "technical": {
            "rsi": _r(v_rsi),
            "macd": _r(v_macd, 3),
            "macd_signal": _r(v_signal, 3),
            "macd_hist": _r(v_hist, 3),
            "sma20": _r(v_sma20),
            "sma50": _r(v_sma50),
            "sma200": _r(v_sma200),
            "golden_cross": golden_cross,
            "high_52w": round(high_52, 2),
            "low_52w": round(low_52, 2),
            "pct_from_high_52w": round((price / high_52 - 1) * 100, 2) if high_52 else 0,
            "drawdown": round(drawdown, 2),
        },
        "returns": {
            "w1": _r(ret_1w), "m1": _r(ret_1m), "m3": _r(ret_3m),
            "m6": _r(ret_6m), "y1": _r(ret_1y),
        },
        "fundamentals": fundamentals or {},
        "series": {
            "dates": dates[s:],
            "close": [round(c, 2) for c in closes[s:]],
            "volume": [int(v) for v in volumes[s:]],
            "sma50": [_r(x) for x in sma50[s:]],
            "sma200": [_r(x) for x in sma200[s:]],
            "bb_up": [_r(x) for x in bb_up[s:]],
            "bb_low": [_r(x) for x in bb_low[s:]],
            "rsi": [_r(x) for x in rsi14[s:]],
            "macd": [_r(x, 3) for x in macd_line[s:]],
            "macd_signal": [_r(x, 3) for x in signal_line[s:]],
            "macd_hist": [_r(x, 3) for x in hist[s:]],
        },
    }


def _recent_volatility(closes: List[float], period: int) -> Optional[float]:
    if len(closes) <= period:
        return None
    window = closes[-period - 1 :]
    rets = [
        (window[i] / window[i - 1] - 1)
        for i in range(1, len(window))
        if window[i - 1]
    ]
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    return (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5


def _r(v: Optional[float], nd: int = 2) -> Optional[float]:
    return round(v, nd) if v is not None else None


def market_summary(indices: List[Dict]) -> Dict:
    """Sintesi complessiva del mercato aggregando i tre indici."""
    scores = [i["score"] for i in indices]
    avg = sum(scores) / len(scores) if scores else 50
    bull = sum(1 for i in indices if i["verdict"] == "Bullish")
    bear = sum(1 for i in indices if i["verdict"] == "Bearish")
    if avg >= 62:
        phase = "Bullish"
        desc = "Il quadro tecnico complessivo e' positivo: trend rialzista prevalente."
    elif avg <= 42:
        phase = "Bearish"
        desc = "Il quadro tecnico complessivo e' negativo: prevalgono le pressioni ribassiste."
    else:
        phase = "Neutrale"
        desc = "Mercato in fase laterale/incerta: segnali contrastanti tra gli indici."
    avg_risk = sum(i["correction_risk"] for i in indices) / len(indices) if indices else 0
    return {
        "phase": phase,
        "avg_score": round(avg, 1),
        "description": desc,
        "bullish_count": bull,
        "bearish_count": bear,
        "avg_correction_risk": round(avg_risk, 0),
    }
