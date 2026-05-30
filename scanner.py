"""
╔══════════════════════════════════════════════════════════════╗
║       MOMENTUM SWING TRADER — DAILY SCANNER v1              ║
║       Paper Trading Simulator | Starting ₹50,000            ║
║       Strategy: v9 Parameters (Beat Nifty by 2.1% CAGR)    ║
╚══════════════════════════════════════════════════════════════╝

HOW TO RUN:

  Manual (run once today):
    python scanner.py

  Auto-scheduler (runs at 4:15 PM IST every weekday):
    python scanner.py --schedule
    (keep this terminal open)

  Reset portfolio (start fresh):
    python scanner.py --reset

FIRST TIME SETUP:
  1. Place nifty500.csv in same folder (download from nseindia.com)
  2. pip install yfinance pandas numpy schedule requests
  3. python scanner.py
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import sys
import time
import requests
import schedule
from datetime import datetime, date
from pathlib import Path

# ================================================================
# STRATEGY PARAMETERS (locked from v9 backtest)
# ================================================================
STRATEGY = {
    # Capital
    'initial_capital'         : 50_000,
    'max_positions'           : 5,

    # Entry signals
    'rsi_period'              : 14,
    'rsi_entry_min'           : 55,
    'rsi_entry_max'           : 70,
    'adx_period'              : 14,
    'adx_min'                 : 25,
    'roc_period'              : 20,
    'roc_min'                 : 5.0,
    'volume_avg_period'       : 20,
    'volume_surge_min'        : 1.5,
    'dma50_confirm_days'      : 3,    # stock must be above 50 DMA for 3+ days
    'momentum_signals_needed' : 2,    # need 2 of 3 momentum signals

    # Exit signals
    'stop_loss_pct'           : 0.05,
    'trailing_activation_pct' : 0.10, # trailing starts after +10% gain
    'trailing_stop_pct'       : 0.07, # trail 7% below peak
    'profit_target_pct'       : 0.15,
    'max_hold_days'           : 65,
    'rsi_exit'                : 78,
    'dma20_exit_days'         : 3,    # exit after 3 days below 20 DMA

    # Regime filter (hybrid)
    'regime_fast_dma'         : 50,
    'regime_slow_dma'         : 200,
    'half_size_multiplier'    : 0.5,  # half position in weak uptrend

    # Data
    'lookback_days'           : 300,  # days of history to fetch
    'transaction_cost'        : 0.002, # 0.2% per side
}

# ================================================================
# FILE PATHS
# ================================================================
BASE_DIR      = Path(__file__).parent
PORTFOLIO_FILE= BASE_DIR / 'portfolio.json'
TRADE_LOG     = BASE_DIR / 'trade_log.csv'
SCAN_LOG      = BASE_DIR / 'scan_log.csv'
UNIVERSE_CSV  = BASE_DIR / 'nifty500.csv'


# ================================================================
# UNIVERSE
# ================================================================
FALLBACK = list(dict.fromkeys([
    'RELIANCE.NS','TCS.NS','HDFCBANK.NS','ICICIBANK.NS','INFY.NS',
    'HINDUNILVR.NS','ITC.NS','SBIN.NS','BHARTIARTL.NS','KOTAKBANK.NS',
    'LT.NS','AXISBANK.NS','ASIANPAINT.NS','MARUTI.NS','SUNPHARMA.NS',
    'TITAN.NS','ULTRACEMCO.NS','BAJFINANCE.NS','NESTLEIND.NS','WIPRO.NS',
    'HCLTECH.NS','POWERGRID.NS','NTPC.NS','TECHM.NS','BAJAJFINSV.NS',
    'ONGC.NS','COALINDIA.NS','GRASIM.NS','ADANIENT.NS','ADANIPORTS.NS',
    'DIVISLAB.NS','DRREDDY.NS','CIPLA.NS','EICHERMOT.NS','BPCL.NS',
    'HEROMOTOCO.NS','INDUSINDBK.NS','SHREECEM.NS','SBILIFE.NS','BRITANNIA.NS',
    'TATACONSUM.NS','APOLLOHOSP.NS','HDFCLIFE.NS','BAJAJ-AUTO.NS','TATAPOWER.NS',
    'GAIL.NS','HINDALCO.NS','JSWSTEEL.NS','TATASTEEL.NS','VEDL.NS',
    'ICICIPRULI.NS','ICICIGI.NS','HDFCAMC.NS','PIDILITIND.NS','GODREJCP.NS',
    'HAVELLS.NS','MARICO.NS','DABUR.NS','BERGEPAINT.NS','COLPAL.NS',
    'SIEMENS.NS','BOSCHLTD.NS','CUMMINSIND.NS','TORNTPHARM.NS','ALKEM.NS',
    'AUROPHARMA.NS','LUPIN.NS','BIOCON.NS','MUTHOOTFIN.NS','CHOLAFIN.NS',
    'TVSMOTOR.NS','MRF.NS','DLF.NS','GODREJPROP.NS','INDIGO.NS',
    'IRCTC.NS','CONCOR.NS','ADANIGREEN.NS','TORNTPOWER.NS','IGL.NS',
    'PETRONET.NS','NMDC.NS','HINDZINC.NS','BANDHANBNK.NS','FEDERALBNK.NS',
    'IDFCFIRSTB.NS','PERSISTENT.NS','COFORGE.NS','MPHASIS.NS','OFSS.NS',
    'VOLTAS.NS','PAGEIND.NS','TRENT.NS','JUBLFOOD.NS','POLYCAB.NS',
    'LALPATHLAB.NS','MAXHEALTH.NS','FORTIS.NS','MANAPPURAM.NS','SUNDARMFIN.NS',
    'CDSL.NS','NAUKRI.NS','AFFLE.NS','ASTRAL.NS','SUPREMEIND.NS',
    'DIXON.NS','AMBER.NS','PIIND.NS','SUMICHEM.NS','AARTIIND.NS','SRF.NS',
    'ATUL.NS','SCHAEFFLER.NS','TIMKEN.NS','SKFINDIA.NS','GRINDWELL.NS',
    'BALKRISIND.NS','APOLLOTYRE.NS','ESCORTS.NS','ASHOKLEY.NS','BATAINDIA.NS',
    'RELAXO.NS','ABFRL.NS','KPIL.NS','KEC.NS','APLAPOLLO.NS',
    'RATNAMANI.NS','NATIONALUM.NS','IPCALAB.NS','GLAXO.NS','PFIZER.NS',
    'OBEROIRLTY.NS','PRESTIGE.NS','PHOENIXLTD.NS','ABB.NS','WHIRLPOOL.NS',
    'BLUESTARCO.NS','PVRINOX.NS','SUNTV.NS','METROPOLIS.NS','NH.NS',
    'CANFINHOME.NS','ANGELONE.NS','BSE.NS','JUSTDIAL.NS','CAMS.NS',
    'ROUTE.NS','TANLA.NS','LINDEINDIA.NS','MOTHERSON.NS','SAIL.NS',
    'MGL.NS','RBLBANK.NS','DEVYANI.NS','WESTLIFE.NS','UPL.NS',
    'ZYDUSLIFE.NS','TATACOMM.NS','MFSL.NS','RADICO.NS','JKCEMENT.NS',
    'TATAELXSI.NS','LTTS.NS','KPITTECH.NS','CYIENT.NS','INTELLECT.NS',
    'NAVINFLUOR.NS','FLUOROCHEM.NS','DEEPAKFERT.NS','GNFC.NS',
    'GSFC.NS','COROMANDEL.NS','EDELWEISS.NS','UBL.NS','AVANTIFEED.NS',
]))


def get_universe():
    if UNIVERSE_CSV.exists():
        try:
            df         = pd.read_csv(UNIVERSE_CSV)
            df.columns = [c.strip().replace('\n','').replace('\r','') for c in df.columns]
            sym_col    = next((c for c in df.columns if c.strip().upper() == 'SYMBOL'), df.columns[0])
            syms       = df[sym_col].astype(str).str.strip()
            bad        = {'NIFTY 500','NIFTY500','NIFTY200','NIFTY 200',
                          'NIFTY100','NIFTY 100','NIFTY50','NIFTY 50'}
            syms       = syms[~syms.str.upper().isin(bad)]
            syms       = syms[(syms.str.len() > 0) & (syms.str.lower() != 'nan')]
            result     = (syms + '.NS').tolist()
            if len(result) >= 50:
                return result
        except Exception:
            pass
    return FALLBACK


# ================================================================
# PORTFOLIO STATE
# ================================================================

def load_portfolio():
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    # First time — create fresh portfolio
    return {
        'start_date'      : str(date.today()),
        'initial_capital' : STRATEGY['initial_capital'],
        'cash'            : float(STRATEGY['initial_capital']),
        'positions'       : {},      # {ticker: {entry_price, entry_date, shares, invested, highest_price, score}}
        'pending_buys'    : [],      # signals from yesterday → execute at today's open
        'completed_trades': [],      # full history
        'last_run_date'   : None,
    }


def save_portfolio(p):
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(p, f, indent=2, default=str)


# ================================================================
# INDICATORS (same as v9)
# ================================================================

def compute_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    return 100 - (100 / (1 + avg_gain / (avg_loss + 1e-10)))


def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast    = series.ewm(span=fast, min_periods=fast).mean()
    ema_slow    = series.ewm(span=slow, min_periods=slow).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, signal_line


def compute_adx(high, low, close, period=14):
    tr1  = high - low
    tr2  = (high - close.shift(1)).abs()
    tr3  = (low  - close.shift(1)).abs()
    tr   = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    up   = high - high.shift(1)
    down = low.shift(1) - low
    pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=close.index)
    mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=close.index)
    atr  = tr.ewm(alpha=1/period, min_periods=period).mean()
    pdi  = 100 * pdm.ewm(alpha=1/period, min_periods=period).mean() / (atr + 1e-10)
    mdi  = 100 * mdm.ewm(alpha=1/period, min_periods=period).mean() / (atr + 1e-10)
    dx   = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-10)
    return dx.ewm(alpha=1/period, min_periods=period).mean()


def flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df


def compute_indicators(df):
    s = STRATEGY
    df = df.copy()
    df['rsi']              = compute_rsi(df['Close'], s['rsi_period'])
    df['macd'], df['macd_sig'] = compute_macd(df['Close'])
    df['adx']              = compute_adx(df['High'], df['Low'], df['Close'], s['adx_period'])
    df['roc']              = df['Close'].pct_change(s['roc_period']) * 100
    df['dma20']            = df['Close'].rolling(20).mean()
    df['dma50']            = df['Close'].rolling(50).mean()
    df['dma200']           = df['Close'].rolling(200).mean()
    df['vol_avg']          = df['Volume'].rolling(s['volume_avg_period']).mean()
    df['vol_ratio']        = df['Volume'] / (df['vol_avg'] + 1e-10)
    df['macd_bull']        = (df['macd'] > df['macd_sig']) & (df['macd'].shift(1) <= df['macd_sig'].shift(1))
    df['above_dma50']      = (df['Close'] > df['dma50']).astype(int)
    df['dma50_days_above'] = df['above_dma50'].rolling(s['dma50_confirm_days']).sum()
    df['below_dma20']      = (df['Close'] < df['dma20']).astype(int)
    df['dma20_days_below'] = df['below_dma20'].rolling(s['dma20_exit_days']).sum()
    return df


# ================================================================
# DATA DOWNLOAD
# ================================================================

def download_data(tickers):
    """Download recent OHLCV data for all tickers."""
    from datetime import timedelta
    end   = datetime.today().strftime('%Y-%m-%d')
    # Fetch enough history for 200 DMA
    start = (datetime.today() - timedelta(days=STRATEGY['lookback_days'])).strftime('%Y-%m-%d')

    print(f"  Downloading data for {len(tickers)} stocks...", end=' ', flush=True)
    all_data = {}
    batches  = [tickers[i:i+50] for i in range(0, len(tickers), 50)]

    for batch in batches:
        try:
            raw = yf.download(batch, start=start, end=end,
                              group_by='ticker', auto_adjust=True,
                              progress=False, threads=True)
            for ticker in batch:
                try:
                    df = raw[ticker].copy() if len(batch) > 1 else raw.copy()
                    df = flatten(df)
                    df = df.dropna(subset=['Close'])
                    if len(df) >= 60:
                        all_data[ticker] = compute_indicators(df)
                except Exception:
                    pass
        except Exception as e:
            pass
        time.sleep(0.2)

    # Also get Nifty 50 for regime
    try:
        nifty = yf.download('^NSEI', start=start, end=end, auto_adjust=True, progress=False)
        nifty = flatten(nifty)
        all_data['__NIFTY__'] = compute_indicators(nifty)
    except Exception:
        pass

    print(f"✅ {len(all_data)-1} stocks loaded")
    return all_data


# ================================================================
# REGIME DETECTION
# ================================================================

def get_regime(all_data):
    """
    Returns:
      2 = Strong uptrend (Nifty above both 50 DMA and 200 DMA) → full position
      1 = Weak uptrend   (Nifty above 200 DMA, below 50 DMA)   → half position
      0 = Downtrend      (Nifty below 200 DMA)                  → no new entries
    """
    if '__NIFTY__' not in all_data:
        return 2  # default to allow trading if data unavailable
    nifty = all_data['__NIFTY__']
    row   = nifty.iloc[-1]
    close = float(row['Close'])
    dma50 = float(row['dma50'])  if not pd.isna(row['dma50'])  else 0
    dma200= float(row['dma200']) if not pd.isna(row['dma200']) else 0

    if close > dma200 and close > dma50:
        return 2   # Strong uptrend
    elif close > dma200:
        return 1   # Weak uptrend
    else:
        return 0   # Downtrend


def regime_label(r):
    return {2: '📈 STRONG UPTREND', 1: '〰️  WEAK UPTREND', 0: '📉 DOWNTREND'}[r]


# ================================================================
# SIGNAL FUNCTIONS (v9 strategy)
# ================================================================

def get_buy_signal(df):
    """Check if stock has a BUY signal as of today."""
    s   = STRATEGY
    row = df.iloc[-1]

    for col in ['rsi','adx','macd','roc','dma50','vol_ratio','dma50_days_above']:
        if pd.isna(row.get(col, np.nan)):
            return False, 0, {}

    # Hard filters
    if not (s['rsi_entry_min'] <= row['rsi'] <= s['rsi_entry_max']):
        return False, 0, {}
    if row['adx'] < s['adx_min']:
        return False, 0, {}
    if row['Close'] <= row['dma50']:
        return False, 0, {}
    if row['dma50_days_above'] < s['dma50_confirm_days']:
        return False, 0, {}

    # Momentum score
    score  = 0
    checks = {}
    lookback = df.tail(5)
    if lookback['macd_bull'].any():
        score += 1
        checks['MACD Cross'] = '✅'
    else:
        checks['MACD Cross'] = '❌'

    if row['vol_ratio'] >= s['volume_surge_min']:
        score += 1
        checks['Volume Surge'] = f"✅ {row['vol_ratio']:.1f}x"
    else:
        checks['Volume Surge'] = f"❌ {row['vol_ratio']:.1f}x"

    if row['roc'] >= s['roc_min']:
        score += 1
        checks['ROC 20d'] = f"✅ {row['roc']:.1f}%"
    else:
        checks['ROC 20d'] = f"❌ {row['roc']:.1f}%"

    details = {
        'rsi'   : round(float(row['rsi']), 1),
        'adx'   : round(float(row['adx']), 1),
        'roc'   : round(float(row['roc']), 1),
        'close' : round(float(row['Close']), 2),
        'dma50' : round(float(row['dma50']), 2),
        'score' : score,
        'checks': checks,
    }

    return (score >= s['momentum_signals_needed']), score, details


def check_exit(position, df):
    """
    Check exit conditions for a held position.
    Returns (should_exit, reason, current_price, updated_highest_price)
    """
    s          = STRATEGY
    row        = df.iloc[-1]
    cur_price  = float(row['Close'])
    entry_price= float(position['entry_price'])
    entry_date = pd.to_datetime(position['entry_date'])
    cur_date   = df.index[-1]
    highest    = max(float(position.get('highest_price', entry_price)), cur_price)

    pct_entry  = (cur_price - entry_price) / entry_price
    pct_peak   = (highest - entry_price) / entry_price

    # 1. Profit target
    if pct_entry >= s['profit_target_pct']:
        return True, f"🎯 Profit Target (+{pct_entry*100:.1f}%)", cur_price, highest

    # 2. Trailing / hard stop
    if pct_peak >= s['trailing_activation_pct']:
        eff_stop = max(highest * (1 - s['trailing_stop_pct']),
                       entry_price * (1 - s['stop_loss_pct']))
        if cur_price <= eff_stop:
            return True, f"🔻 Trailing Stop ({pct_entry*100:+.1f}%)", cur_price, highest
    else:
        if pct_entry <= -s['stop_loss_pct']:
            return True, f"🛑 Stop Loss ({pct_entry*100:.1f}%)", cur_price, highest

    # 3. Time stop
    days_held = (cur_date - entry_date).days
    if days_held >= s['max_hold_days']:
        return True, f"⏱️  Time Stop ({days_held}d, {pct_entry*100:+.1f}%)", cur_price, highest

    # 4. RSI overbought
    if not pd.isna(row.get('rsi', np.nan)) and row['rsi'] > s['rsi_exit']:
        return True, f"📈 RSI Overbought ({row['rsi']:.1f})", cur_price, highest

    # 5. Below 20 DMA for 3+ days
    if not pd.isna(row.get('dma20_days_below', np.nan)):
        if row['dma20_days_below'] >= s['dma20_exit_days']:
            return True, f"📉 Below 20 DMA ({s['dma20_exit_days']} days)", cur_price, highest

    return False, "", cur_price, highest


# ================================================================
# DAILY SCAN LOGIC
# ================================================================

def run_scan():
    now = datetime.now()
    print("\n" + "═"*62)
    print(f"  🔍 MOMENTUM SCANNER — {now.strftime('%A, %d %b %Y  %I:%M %p')}")
    print("═"*62)

    # Load state
    portfolio = load_portfolio()

    # Check if already run today (prevent duplicate runs)
    today_str = str(date.today())
    if portfolio.get('last_run_date') == today_str:
        if '--force' not in sys.argv:
            print(f"\n  ⚠️  Already ran today ({today_str}).")
            print("     Run with --force to override.")
            return

    # Load universe and download data
    universe = get_universe()
    print(f"\n  Universe: {len(universe)} stocks")
    all_data = download_data(universe)

    # Get market regime
    regime = get_regime(all_data)
    print(f"  Market:   {regime_label(regime)}")
    print()

    exits_today    = []
    buys_executed  = []
    buys_pending   = []

    # ── STEP 1: Execute yesterday's pending buys at TODAY's open ──
    still_pending = []
    for ticker in portfolio.get('pending_buys', []):
        if ticker not in all_data:
            still_pending.append(ticker)
            continue
        if ticker in portfolio['positions']:
            continue  # already holding this somehow

        df          = all_data[ticker]
        today_open  = float(df.iloc[-1]['Open'])
        free_slots  = STRATEGY['max_portfolio_size'] - len(portfolio['positions'])

        if free_slots <= 0 or portfolio['cash'] < 500:
            continue
        if pd.isna(today_open) or today_open <= 0:
            continue

        # Position sizing based on yesterday's regime (use today's as proxy)
        regime_at_buy = portfolio.get('pending_regime', {}).get(ticker, 2)
        size_mult     = 1.0 if regime_at_buy == 2 else STRATEGY['half_size_multiplier']
        alloc         = (portfolio['cash'] / max(free_slots, 1)) * size_mult
        cost          = alloc * (1 + STRATEGY['transaction_cost'])
        if cost > portfolio['cash']:
            alloc = portfolio['cash'] / (1 + STRATEGY['transaction_cost'])
            cost  = portfolio['cash']
        if alloc < 100:
            continue

        shares = alloc / today_open
        portfolio['cash'] -= cost
        portfolio['positions'][ticker] = {
            'entry_price'  : today_open,
            'entry_date'   : today_str,
            'shares'       : shares,
            'invested'     : alloc,
            'highest_price': today_open,
            'score'        : portfolio.get('pending_scores', {}).get(ticker, 0),
            'regime'       : 'Strong' if regime_at_buy == 2 else 'Weak',
        }
        buys_executed.append({
            'ticker'    : ticker,
            'price'     : today_open,
            'shares'    : round(shares, 4),
            'invested'  : round(alloc, 2),
            'regime'    : 'Strong' if regime_at_buy == 2 else 'Weak',
        })

    portfolio['pending_buys']   = still_pending
    portfolio['pending_regime'] = {}
    portfolio['pending_scores'] = {}

    # ── STEP 2: Check exits for held positions ────────────────────
    to_exit = []
    for ticker, pos in portfolio['positions'].items():
        if ticker not in all_data:
            continue
        df = all_data[ticker]
        should_exit, reason, cur_price, new_high = check_exit(pos, df)
        portfolio['positions'][ticker]['highest_price'] = new_high

        if should_exit:
            proceeds  = pos['shares'] * cur_price * (1 - STRATEGY['transaction_cost'])
            pnl_pct   = (cur_price / pos['entry_price'] - 1) * 100 - STRATEGY['transaction_cost'] * 100
            pnl_inr   = proceeds - pos['invested']
            portfolio['cash'] += proceeds

            trade = {
                'ticker'      : ticker,
                'entry_date'  : pos['entry_date'],
                'exit_date'   : today_str,
                'entry_price' : pos['entry_price'],
                'exit_price'  : round(cur_price, 2),
                'shares'      : round(pos['shares'], 4),
                'invested'    : round(pos['invested'], 2),
                'proceeds'    : round(proceeds, 2),
                'pnl_pct'     : round(pnl_pct, 2),
                'pnl_inr'     : round(pnl_inr, 2),
                'hold_days'   : (pd.to_datetime(today_str) - pd.to_datetime(pos['entry_date'])).days,
                'exit_reason' : reason,
                'score'       : pos.get('score', 0),
            }
            portfolio['completed_trades'].append(trade)
            exits_today.append(trade)
            to_exit.append(ticker)

    for t in to_exit:
        del portfolio['positions'][t]

    # ── STEP 3: Find new BUY signals ─────────────────────────────
    if regime == 0:
        print("  🚫 Market in DOWNTREND — no new entries today")
    else:
        free_slots = STRATEGY['max_portfolio_size'] - len(portfolio['positions'])
        candidates = []

        for ticker, df in all_data.items():
            if ticker == '__NIFTY__':
                continue
            if ticker in portfolio['positions']:
                continue
            if ticker in portfolio.get('pending_buys', []):
                continue
            is_buy, score, details = get_buy_signal(df)
            if is_buy:
                candidates.append((ticker, score, details))

        candidates.sort(key=lambda x: x[1], reverse=True)

        # Record pending buys (will execute TOMORROW at open)
        new_pending_regime = dict(portfolio.get('pending_regime', {}))
        new_pending_scores = dict(portfolio.get('pending_scores', {}))

        for ticker, score, details in candidates[:free_slots]:
            portfolio['pending_buys'] = portfolio.get('pending_buys', [])
            if ticker not in portfolio['pending_buys']:
                portfolio['pending_buys'].append(ticker)
                new_pending_regime[ticker] = regime
                new_pending_scores[ticker] = score
                buys_pending.append((ticker, score, details))

        portfolio['pending_regime'] = new_pending_regime
        portfolio['pending_scores'] = new_pending_scores

    # ── STEP 4: Update portfolio state ────────────────────────────
    # Calculate current portfolio value
    total_holdings = 0.0
    positions_value = {}
    for ticker, pos in portfolio['positions'].items():
        if ticker in all_data:
            cur_price = float(all_data[ticker].iloc[-1]['Close'])
            val       = pos['shares'] * cur_price
            pct       = (cur_price / pos['entry_price'] - 1) * 100
            total_holdings  += val
            positions_value[ticker] = {
                'cur_price': round(cur_price, 2),
                'value'    : round(val, 2),
                'pnl_pct'  : round(pct, 2),
                'entry_price': pos['entry_price'],
                'entry_date' : pos['entry_date'],
                'hold_days'  : (pd.to_datetime(today_str) - pd.to_datetime(pos['entry_date'])).days,
                'target_price': round(pos['entry_price'] * (1 + STRATEGY['profit_target_pct']), 2),
                'stop_price'  : round(pos['entry_price'] * (1 - STRATEGY['stop_loss_pct']), 2),
                'highest_price': round(pos.get('highest_price', pos['entry_price']), 2),
            }

    total_value   = portfolio['cash'] + total_holdings
    initial_cap   = portfolio['initial_capital']
    total_pnl_pct = (total_value - initial_cap) / initial_cap * 100
    total_pnl_inr = total_value - initial_cap

    portfolio['last_run_date']   = today_str
    portfolio['snapshot_value']  = round(total_value, 2)

    # Save trade log CSV
    if portfolio['completed_trades']:
        pd.DataFrame(portfolio['completed_trades']).to_csv(TRADE_LOG, index=False)

    # Save scan log
    scan_entry = {
        'date'        : today_str,
        'portfolio_val': round(total_value, 2),
        'cash'        : round(portfolio['cash'], 2),
        'n_positions' : len(portfolio['positions']),
        'regime'      : regime_label(regime),
        'exits_today' : len(exits_today),
        'new_signals' : len(buys_pending),
    }
    scan_df = pd.DataFrame([scan_entry])
    if SCAN_LOG.exists():
        existing = pd.read_csv(SCAN_LOG)
        scan_df  = pd.concat([existing, scan_df], ignore_index=True)
    scan_df.to_csv(SCAN_LOG, index=False)

    save_portfolio(portfolio)

    # ── STEP 5: Print daily report ────────────────────────────────
    print()
    print("─"*62)
    print("  💼 PORTFOLIO SUMMARY")
    print("─"*62)
    print(f"  Total Value   : ₹{total_value:>10,.2f}")
    print(f"  Cash          : ₹{portfolio['cash']:>10,.2f}")
    print(f"  Holdings      : ₹{total_holdings:>10,.2f}")
    print(f"  Total P&L     : {'🟢' if total_pnl_inr >= 0 else '🔴'} ₹{total_pnl_inr:>+,.2f}  ({total_pnl_pct:>+.2f}%)")

    # Show completed trades P&L summary
    if portfolio['completed_trades']:
        all_trades = pd.DataFrame(portfolio['completed_trades'])
        wins       = all_trades[all_trades['pnl_pct'] > 0]
        losses     = all_trades[all_trades['pnl_pct'] <= 0]
        print(f"\n  Closed Trades : {len(all_trades)}  "
              f"[✅ {len(wins)} wins  ❌ {len(losses)} losses  "
              f"Win Rate: {len(wins)/len(all_trades)*100:.0f}%]")
        print(f"  Realised P&L  : ₹{all_trades['pnl_inr'].sum():>+,.2f}")

    # Exits today
    if exits_today:
        print(f"\n─"*62)
        print(f"  📤 EXITS TODAY ({len(exits_today)})")
        print("─"*62)
        for t in exits_today:
            icon = '🟢' if t['pnl_inr'] >= 0 else '🔴'
            print(f"  {icon} {t['ticker']:<20} "
                  f"Entry: ₹{t['entry_price']:>8.2f}  "
                  f"Exit: ₹{t['exit_price']:>8.2f}  "
                  f"P&L: ₹{t['pnl_inr']:>+7.2f} ({t['pnl_pct']:>+.1f}%)")
            print(f"     Reason: {t['exit_reason']}  |  Held: {t['hold_days']} days")
    else:
        print(f"\n  📤 No exits today")

    # Buys executed today
    if buys_executed:
        print(f"\n─"*62)
        print(f"  ✅ BOUGHT TODAY (pending from yesterday)")
        print("─"*62)
        for b in buys_executed:
            print(f"  🟢 {b['ticker']:<20} @ ₹{b['price']:.2f}  "
                  f"Invested: ₹{b['invested']:,.2f}  "
                  f"({b['regime']} regime)")

    # Current holdings
    if positions_value:
        print(f"\n─"*62)
        print(f"  📋 CURRENT HOLDINGS ({len(positions_value)}/{STRATEGY['max_portfolio_size']} slots)")
        print("─"*62)
        for ticker, v in positions_value.items():
            icon = '🟢' if v['pnl_pct'] >= 0 else '🔴'
            trail_level = ''
            pos = portfolio['positions'][ticker]
            if (v['cur_price'] / pos['entry_price'] - 1) >= STRATEGY['trailing_activation_pct']:
                trail_stop = max(v['highest_price'] * (1 - STRATEGY['trailing_stop_pct']),
                                 pos['entry_price'] * (1 - STRATEGY['stop_loss_pct']))
                trail_level = f"  Trail: ₹{trail_stop:.2f}"
            print(f"  {icon} {ticker:<20} "
                  f"Entry: ₹{v['entry_price']:>8.2f}  "
                  f"Now: ₹{v['cur_price']:>8.2f}  "
                  f"P&L: {v['pnl_pct']:>+5.1f}%")
            print(f"     Target: ₹{v['target_price']:.2f}  "
                  f"Stop: ₹{v['stop_price']:.2f}{trail_level}  "
                  f"Day {v['hold_days']}")
    else:
        print(f"\n  📋 No open positions")

    # Pending buys for tomorrow
    if portfolio.get('pending_buys'):
        print(f"\n─"*62)
        print(f"  ⏳ PENDING — BUYING TOMORROW AT OPEN")
        print("─"*62)
        for i, (ticker, score, details) in enumerate(buys_pending):
            print(f"  {i+1}. {ticker:<20} Score: {score}/3  "
                  f"RSI: {details['rsi']}  ADX: {details['adx']}  "
                  f"ROC: {details['roc']:+.1f}%")
            for check, status in details.get('checks', {}).items():
                print(f"     {check}: {status}")

    # Watchlist (candidates that didn't make the cut)
    if regime > 0:
        all_candidates = []
        for ticker, df in all_data.items():
            if ticker == '__NIFTY__' or ticker in portfolio['positions']:
                continue
            if ticker in portfolio.get('pending_buys', []):
                continue
            is_buy, score, details = get_buy_signal(df)
            if is_buy:
                all_candidates.append((ticker, score, details))
        all_candidates.sort(key=lambda x: x[1], reverse=True)
        watchlist = [c for c in all_candidates if c[0] not in [b[0] for b in buys_pending]][:5]
        if watchlist:
            print(f"\n─"*62)
            print(f"  👀 WATCHLIST (signals not acted on — portfolio full or already pending)")
            print("─"*62)
            for ticker, score, details in watchlist:
                print(f"  📊 {ticker:<20} Score: {score}/3  "
                      f"RSI: {details['rsi']}  ROC: {details['roc']:+.1f}%")

    print(f"\n─"*62)
    print(f"  ✅ Scan complete — {now.strftime('%H:%M:%S')}")
    print(f"  Next run: tomorrow at 4:15 PM IST (or run manually)")
    print("─"*62 + "\n")


# ================================================================
# MAIN
# ================================================================

def reset_portfolio():
    if PORTFOLIO_FILE.exists():
        PORTFOLIO_FILE.unlink()
    if TRADE_LOG.exists():
        TRADE_LOG.unlink()
    if SCAN_LOG.exists():
        SCAN_LOG.unlink()
    print("✅ Portfolio reset. Starting fresh with ₹50,000.")


if __name__ == '__main__':

    if '--reset' in sys.argv:
        confirm = input("⚠️  This will erase all trades and reset to ₹50,000. Type YES to confirm: ")
        if confirm.strip().upper() == 'YES':
            reset_portfolio()
        else:
            print("Cancelled.")
        sys.exit(0)

    if '--schedule' in sys.argv:
        # Auto-run at 4:15 PM IST every weekday
        print("🕐 Scheduler started. Will run at 4:15 PM IST on weekdays.")
        print("   Keep this terminal open. Press Ctrl+C to stop.\n")

        def scheduled_job():
            if datetime.now().weekday() < 5:   # Monday=0 to Friday=4
                run_scan()
            else:
                print(f"  [{datetime.now().strftime('%H:%M')}] Weekend — market closed, skipping.")

        schedule.every().day.at("16:15").do(scheduled_job)

        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        # Run immediately
        run_scan()