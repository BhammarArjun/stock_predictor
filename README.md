# Momentum Swing Trading — Nifty 500

A momentum-based swing trading system for the Indian equity market (Nifty 500 universe), built around a v9 strategy that combines hybrid market-regime filtering, multi-indicator entry signals, and layered exit rules.

The repo contains two scripts:

- **`backtest.py`** — historical backtest of the strategy from 2015 to today.
- **`scanner.py`** — daily paper-trading scanner that maintains a live ₹50,000 portfolio, finds buy signals, and manages exits.

---

## Strategy (v9) at a glance

**Universe**: Nifty 500 (loaded from `nifty500.csv`, falls back to NSE API, then a built-in list of ~190 large/mid caps).

**Hybrid market regime (3 tiers on Nifty 50):**
| Regime | Condition | Action |
|---|---|---|
| Strong uptrend | Above 50 DMA *and* 200 DMA | Full position size (1/5 of cash) |
| Weak uptrend | Above 200 DMA, below 50 DMA | Half position size |
| Downtrend | Below 200 DMA | No new entries |

**Entry — hard filters (all must pass):**
- RSI(14) between 55 and 70
- ADX(14) > 25
- Close > 50 DMA
- Stock above 50 DMA for 3+ consecutive days (breakout confirmation)

**Entry — momentum confirmation (need 2 of 3):**
- MACD bullish crossover within last 5 days
- Volume surge ≥ 1.5× 20-day average
- 20-day Rate of Change ≥ 5%

**Exits (priority order):**
1. Profit target +15%
2. Trailing stop — activates at +10%, trails 7% below peak (floor at −5%)
3. Hard stop −5% (before trailing activates)
4. Time stop — 65 days
5. RSI > 78 (overbought)
6. Below 20 DMA for 3 consecutive days

Max 5 concurrent positions. Transaction cost: 0.2% per side.

---

## Installation

Requires Python 3.9+.

```bash
git clone https://github.com/BhammarArjun/stock_predictor.git
cd stock_predictor

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install yfinance pandas numpy requests schedule
```

**Optional but recommended** — download the full Nifty 500 list:

1. Go to https://www.nseindia.com/market-data/live-equity-market
2. Select index **NIFTY 500** → Download (.csv)
3. Save the file as `nifty500.csv` in the repo root.

Without it, the scripts try the NSE API and then fall back to a built-in ~190-stock list.

---

## Usage

### Backtest (2015 → today)

```bash
python backtest.py
```

Outputs:
- Console: capital growth, CAGR, Sharpe, max drawdown, win rate, Nifty 50 comparison, year-by-year breakdown, exit-reason histogram, top 10 trades.
- `trade_log.csv` — every completed trade.
- `portfolio_value.csv` — daily portfolio value, cash, holdings, regime.

### Daily scanner (paper trading)

Run once (after market close):
```bash
python scanner.py
```

Auto-run at 4:15 PM IST every weekday (keep terminal open):
```bash
python scanner.py --schedule
```

Reset the paper portfolio back to ₹50,000:
```bash
python scanner.py --reset
```

Force a second run on the same day:
```bash
python scanner.py --force
```

The scanner workflow:
1. Executes yesterday's pending buys at today's open.
2. Checks exit conditions on current holdings.
3. Scans the universe for new buy signals — queued to execute at tomorrow's open.
4. Prints a portfolio summary, exits, holdings (with target/stop/trail levels), pending buys, and a watchlist.

Scanner state files (auto-created):
- `portfolio.json` — cash, positions, pending buys, completed trades.
- `trade_log.csv` — closed trades.
- `scan_log.csv` — one row per scan.

---

## Files

| File | Purpose |
|---|---|
| `backtest.py` | Historical backtest engine |
| `scanner.py` | Daily paper-trading scanner |
| `nifty500.csv` | Universe (optional; user-supplied) |
| `portfolio.json` | Scanner state (auto-generated) |
| `trade_log.csv` | Completed trades (auto-generated) |
| `portfolio_value.csv` | Daily backtest equity curve (auto-generated) |
| `scan_log.csv` | Scanner run history (auto-generated) |

---

## Disclaimer

This is a research / paper-trading project. Past performance from the backtest does not guarantee future returns. Do your own due diligence before risking real capital.
