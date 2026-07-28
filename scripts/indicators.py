"""
Motore di calcolo per indicatori tecnici.
Funzioni pure in Python standard (nessuna dipendenza esterna): lavorano su
liste di float, così possono essere usate sia dal fetcher reale (dati Yahoo)
sia dal generatore di dati demo.
"""
from __future__ import annotations

from typing import List, Optional


def sma(values: List[float], period: int) -> List[Optional[float]]:
    """Media mobile semplice. Ritorna una lista della stessa lunghezza,
    con None dove non ci sono abbastanza dati."""
    out: List[Optional[float]] = []
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out.append(running / period)
        else:
            out.append(None)
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Media mobile esponenziale."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    # seed con SMA dei primi `period` valori
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """RSI con smoothing di Wilder."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        ch = values[i] - values[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_avg(avg_gain, avg_loss)
    for i in range(period + 1, n):
        ch = values[i] - values[i - 1]
        gain = ch if ch > 0 else 0.0
        loss = -ch if ch < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from_avg(avg_gain, avg_loss)
    return out


def _rsi_from_avg(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD classico. Ritorna (macd_line, signal_line, histogram)."""
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line: List[Optional[float]] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)
    # signal = EMA del macd_line (solo sulla parte valida)
    valid = [v for v in macd_line if v is not None]
    start = len(macd_line) - len(valid)
    sig_valid = ema(valid, signal)
    signal_line: List[Optional[float]] = [None] * len(macd_line)
    for i, v in enumerate(sig_valid):
        signal_line[start + i] = v
    hist: List[Optional[float]] = []
    for m, s in zip(macd_line, signal_line):
        if m is None or s is None:
            hist.append(None)
        else:
            hist.append(m - s)
    return macd_line, signal_line, hist


def bollinger(values: List[float], period: int = 20, mult: float = 2.0):
    """Bande di Bollinger. Ritorna (mid, upper, lower)."""
    mid = sma(values, period)
    upper: List[Optional[float]] = [None] * len(values)
    lower: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i >= period - 1:
            window = values[i - period + 1 : i + 1]
            m = mid[i]
            std = (sum((x - m) ** 2 for x in window) / period) ** 0.5
            upper[i] = m + mult * std
            lower[i] = m - mult * std
    return mid, upper, lower


def pct_return(values: List[float], lookback: int) -> Optional[float]:
    """Rendimento percentuale rispetto a `lookback` barre fa."""
    if len(values) <= lookback or values[-lookback - 1] == 0:
        return None
    return (values[-1] / values[-lookback - 1] - 1) * 100


def last_valid(seq: List[Optional[float]]) -> Optional[float]:
    for v in reversed(seq):
        if v is not None:
            return v
    return None


def max_drawdown_from_high(values: List[float]) -> float:
    """Drawdown percentuale corrente rispetto al massimo del periodo."""
    if not values:
        return 0.0
    peak = max(values)
    if peak == 0:
        return 0.0
    return (values[-1] / peak - 1) * 100


def max_drawdown(values: List[float]) -> float:
    """Massimo drawdown del periodo: la peggior discesa picco-minimo
    (valore piu' negativo), in percentuale."""
    if len(values) < 2:
        return 0.0
    peak = values[0]
    mdd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak:
            dd = (v / peak - 1) * 100
            if dd < mdd:
                mdd = dd
    return mdd
