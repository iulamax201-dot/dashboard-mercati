# 📊 Dashboard Mercati — S&P 500 · Dow Jones · Nasdaq

Dashboard web che si aggiorna da sola con grafici e **analisi tecnica e
fondamentale** dei tre principali indici azionari USA, un **verdetto
Bullish / Bearish / Neutrale** motivato e un **indicatore di rischio correzione**.

- **S&P 500** (`^GSPC`)
- **Dow Jones** (`^DJI`)
- **Nasdaq** (`^IXIC`)

## Come funziona

```
GitHub Actions (ogni 30 min)          GitHub Pages
┌───────────────────────────┐        ┌────────────────────┐
│ scripts/fetch_data.py      │  →     │ docs/index.html     │
│  • scarica dati Yahoo      │ scrive │  • legge data.json  │
│  • calcola indicatori      │ docs/  │  • disegna grafici  │
│  • scrive docs/data.json   │ data.json  (Chart.js)        │
└───────────────────────────┘        └────────────────────┘
```

Nessuna chiave API a pagamento: i dati arrivano dagli endpoint pubblici di
Yahoo Finance (con fallback su Stooq). L'analisi è calcolata in Python puro.

## 🚀 Attivazione (una volta sola)

Dopo aver unito questo branch in `main`:

1. **Abilita GitHub Pages**
   Vai su **Settings → Pages** → in *Source* scegli **Deploy from a branch** →
   Branch **`main`**, cartella **`/docs`** → *Save*.
   Dopo ~1 minuto la dashboard sarà online su:
   `https://iulamax201-dot.github.io/dashboard-mercati/`

2. **Attiva l'aggiornamento automatico**
   Vai su **Actions**, se richiesto abilita i workflow, apri
   *"Aggiorna dati mercati"* e premi **Run workflow** per il primo aggiornamento
   reale. Poi girerà da solo ogni 30 minuti.
   > Nota: i workflow schedulati (`cron`) partono **solo dal branch di default**
   > (`main`), quindi l'automatismo si attiva dopo il merge.

Finché non parte il primo aggiornamento reale, la dashboard mostra **dati
dimostrativi** (chiaramente etichettati come "demo").

## 🧮 Cosa calcola

**Analisi tecnica**
- Medie mobili SMA 20 / 50 / 200 e stato **golden cross / death cross**
- **RSI (14)** con soglie ipercomprato/ipervenduto
- **MACD (12·26·9)** con istogramma
- Bande di Bollinger (20·2σ)
- Range 52 settimane, drawdown dai massimi, rendimenti 1S/1M/3M/6M/1A

**Analisi fondamentale** (via ETF proxy SPY / DIA / QQQ, perché gli indici
non hanno un P/E diretto)
- P/E trailing, dividend yield, beta e commento sulla valutazione

**Titoli Nasdaq 100** (sezione dedicata, tabella ordinabile/filtrabile)
- Quotazioni e mini-grafico per ~100 titoli
- Segnale operativo **Compra / Mantieni / Vendi** (analisi tecnica)
- **Fair value** = target di consenso analisti (Yahoo Finance) + % di upside
- **Sentiment** (tecnico + consenso analisti) e P/E, capitalizzazione
- **Notizie recenti** per ogni titolo (best-effort)
- La composizione dell'indice è in `scripts/nasdaq100.py`, facilmente aggiornabile

> Nota: «fair value» è il target di consenso degli analisti, non una
> valutazione intrinseca (DCF). Il «sentiment» deriva da tecnica + consenso
> analisti, non da analisi NLP di news/social. Tutto a scopo informativo.

**Verdetto e rischio**
- Punteggio 0–100 → **Bullish / Neutrale / Bearish** con motivazioni esplicite
- **Rischio correzione** euristico (0–100) basato su RSI, estensione dalle
  medie, Bollinger e volatilità

## 🛠️ Sviluppo locale

```bash
# genera dati dimostrativi (nessuna rete richiesta)
python scripts/seed_data.py

# oppure scarica dati reali (richiede internet)
pip install -r requirements.txt
python scripts/fetch_data.py

# apri la dashboard
python -m http.server -d docs 8000   # → http://localhost:8000
```

## 📁 Struttura

| File | Ruolo |
|------|-------|
| `docs/index.html` | Interfaccia dashboard (Chart.js) |
| `docs/data.json` | Dati e analisi dei 3 indici |
| `docs/stocks.json` | Dati e analisi dei ~100 titoli Nasdaq |
| `scripts/fetch_data.py` | Fetcher indici (Yahoo/Stooq) |
| `scripts/fetch_stocks.py` | Fetcher titoli Nasdaq 100 |
| `scripts/nasdaq100.py` | Lista costituenti Nasdaq 100 |
| `scripts/stock_analysis.py` | Segnali/sentiment/fair value per titolo |
| `scripts/seed_data.py`, `seed_stocks.py` | Generatori dati demo offline |
| `scripts/analysis.py` | Verdetto e rischio correzione (indici) |
| `scripts/indicators.py` | Motore indicatori (RSI, MACD, SMA, …) |
| `.github/workflows/update-data.yml` | Aggiornamento indici (ogni 15 min) |
| `.github/workflows/update-stocks.yml` | Aggiornamento titoli (ogni 30 min) |

## ⚠️ Disclaimer

Strumento a **scopo informativo ed educativo**. **Non è consulenza
finanziaria** né sollecitazione all'investimento. Il "rischio correzione" è un
indicatore statistico euristico, **non una previsione**: i mercati possono
restare estesi a lungo. I dati possono essere ritardati. Verifica sempre da
fonti ufficiali prima di operare.
