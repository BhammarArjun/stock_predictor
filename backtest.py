"""
╔══════════════════════════════════════════════════════════════╗
║         MOMENTUM SWING TRADING — BACKTEST SCRIPT  v9        ║
║         Universe : Nifty 500 (NSE CSV or fallback)          ║
║         Strategy : Momentum + Hybrid Regime + DMA Confirm   ║
╚══════════════════════════════════════════════════════════════╝

CHANGES IN v9 (vs v8):
    1. ✅ Hybrid Regime Filter — 3 tiers instead of binary:
          Nifty above 50 DMA AND 200 DMA → FULL position size (20% per slot)
          Nifty above 200 DMA, below 50 DMA → HALF position size (10% per slot)
          Nifty below 200 DMA → NO new entries

          Rationale: In choppy markets (above 200 but below 50 DMA),
          we still participate but with smaller bets so stop losses
          hurt less. Best of both v7 and v8.

    2. ✅ Stock must be above its 50 DMA for 3+ consecutive days before entry
          Previously we bought stocks the same day they crossed above DMA.
          Many of those were false breakouts → immediate stop loss.
          3-day confirmation filters out fake pops.

HOW TO GET FULL NIFTY 500:
    1. Go to: https://www.nseindia.com/market-data/live-equity-market
    2. Select Index: "NIFTY 500" → Download (.csv) → Save as "nifty500.csv"

HOW TO RUN:
    python backtest.py
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import time
import sys
import os
import requests

warnings.filterwarnings('ignore')

# ================================================================
# CONFIGURATION
# ================================================================
CONFIG = {
    'start_date'              : '2015-01-01',
    'end_date'                : datetime.today().strftime('%Y-%m-%d'),
    'max_portfolio_size'      : 5,

    # Stop loss
    'stop_loss_pct'           : 0.05,

    # Trailing stop
    'trailing_activation_pct' : 0.10,     # activates after +10% gain
    'trailing_stop_pct'       : 0.07,     # trail 7% below peak

    # Profit target
    'profit_target_pct'       : 0.15,

    # Time stop
    'max_hold_days'           : 65,

    # RSI
    'rsi_period'              : 14,
    'rsi_entry_min'           : 55,
    'rsi_entry_max'           : 70,
    'rsi_exit'                : 78,

    # Rate of Change
    'roc_period'              : 20,
    'roc_min'                 : 5.0,

    # Moving Averages
    'dma_short'               : 20,
    'dma_long'                : 50,
    'dma_exit_days'           : 3,

    # ✅ v9: Stock must be above 50 DMA for this many days before entry
    'dma50_confirm_days'      : 3,

    # Volume
    'volume_avg_period'       : 20,
    'volume_surge_min'        : 1.5,

    # ADX
    'adx_period'              : 14,
    'adx_min'                 : 25,

    # ✅ v9: Hybrid Regime — two DMAs, three tiers
    'regime_fast_dma'         : 50,       # short-term trend
    'regime_slow_dma'         : 200,      # long-term trend
    'half_size_pct'           : 0.5,      # position size multiplier in choppy market

    # Costs
    'cost_per_side'           : 0.002,

    # Capital
    'initial_capital'         : 1_000_000,

    # Entry conviction
    'momentum_conditions_min' : 2,
}


# ================================================================
# UNIVERSE
# ================================================================

def load_from_manual_csv():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nifty500.csv')
    if not os.path.exists(csv_path):
        return None
    try:
        df         = pd.read_csv(csv_path)
        df.columns = [c.strip().replace('\n','').replace('\r','') for c in df.columns]
        sym_col    = next((c for c in df.columns if c.strip().upper() == 'SYMBOL'), df.columns[0])
        symbols_raw= df[sym_col].astype(str).str.strip()
        bad        = {'NIFTY 500','NIFTY500','NIFTY200','NIFTY 200','NIFTY100','NIFTY 100','NIFTY50','NIFTY 50'}
        symbols_raw= symbols_raw[~symbols_raw.str.upper().isin(bad)]
        symbols_raw= symbols_raw[(symbols_raw.str.len() > 0) & (symbols_raw.str.lower() != 'nan')]
        symbols    = (symbols_raw + '.NS').tolist()
        if len(symbols) >= 50:
            print(f"  ✅ Loaded {len(symbols)} stocks from nifty500.csv")
            return symbols
        return None
    except Exception as e:
        print(f"  ⚠️  Could not read nifty500.csv: {e}")
        return None


def fetch_from_nse_api():
    print("  Trying NSE India API...", end=' ', flush=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/',
    }
    session = requests.Session()
    try:
        session.get('https://www.nseindia.com', headers=headers, timeout=10)
        time.sleep(1.5)
        resp = session.get(
            'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500',
            headers={**headers, 'Referer': 'https://www.nseindia.com/market-data/live-equity-market'},
            timeout=10
        )
        if resp.status_code == 200:
            records = resp.json().get('data', [])
            symbols = [r['symbol']+'.NS' for r in records if r.get('symbol') and 'NIFTY' not in r['symbol']]
            if len(symbols) > 400:
                print(f"✅  Got {len(symbols)} stocks")
                return symbols
        print(f"❌  Status {resp.status_code}")
    except Exception as e:
        print(f"❌  ({type(e).__name__})")
    return None


FALLBACK_UNIVERSE = list(dict.fromkeys([
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
    'RAMCOCEM.NS','DALBHARAT.NS','ALKYLAMINE.NS','GALAXYSURF.NS',
    'VINATIORGA.NS','FINEORG.NS','BAYERCROP.NS','RALLIS.NS',
    'TATAELXSI.NS','LTTS.NS','KPITTECH.NS','CYIENT.NS','INTELLECT.NS',
    'MASTEK.NS','KARURVYSYA.NS','CSBBANK.NS','DCBBANK.NS',
    'UJJIVANSFB.NS','EQUITASBNK.NS','CHOLAHLDNG.NS','SUNDRMFAST.NS',
    'SUPRAJIT.NS','ENDURANCE.NS','LUMAXTECH.NS','VGUARD.NS',
    'CROMPTON.NS','ORIENTELEC.NS','AIAENG.NS','GREAVESCOT.NS',
    'ELGIEQUIP.NS','THYROCARE.NS','KRBL.NS','AVANTIFEED.NS',
    'TTKPRESTIG.NS','BAJAJCON.NS','EMAMILTD.NS','GILLETTE.NS',
    'PGHH.NS','JYOTHYLAB.NS','ZYDUSWELL.NS','IIFL.NS',
    'NAVINFLUOR.NS','FLUOROCHEM.NS','DEEPAKFERT.NS','GNFC.NS',
    'GSFC.NS','COROMANDEL.NS','EDELWEISS.NS','UBL.NS',
]))


def get_universe():
    print("\n🌐 Loading Nifty 500 stock universe...")
    symbols = load_from_manual_csv()
    if symbols:
        return symbols
    print("  nifty500.csv not found. Trying auto-fetch...")
    symbols = fetch_from_nse_api()
    if symbols:
        return symbols
    print(f"  ⚠️  Using fallback list ({len(FALLBACK_UNIVERSE)} stocks)")
    return FALLBACK_UNIVERSE


# ================================================================
# INDICATORS
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
    tr1      = high - low
    tr2      = (high - close.shift(1)).abs()
    tr3      = (low  - close.shift(1)).abs()
    tr       = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    up       = high - high.shift(1)
    down     = low.shift(1) - low
    plus_dm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=close.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=close.index)
    atr      = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1/period, min_periods=period).mean() / (atr + 1e-10)
    minus_di = 100 * minus_dm.ewm(alpha=1/period, min_periods=period).mean() / (atr + 1e-10)
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    return dx.ewm(alpha=1/period, min_periods=period).mean()


def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df


def compute_indicators(df):
    c = CONFIG
    df = df.copy()
    df['rsi']              = compute_rsi(df['Close'], c['rsi_period'])
    df['macd'], df['macd_sig'] = compute_macd(df['Close'])
    df['adx']              = compute_adx(df['High'], df['Low'], df['Close'], c['adx_period'])
    df['roc']              = df['Close'].pct_change(c['roc_period']) * 100
    df['dma20']            = df['Close'].rolling(c['dma_short']).mean()
    df['dma50']            = df['Close'].rolling(c['dma_long']).mean()
    df['vol_avg']          = df['Volume'].rolling(c['volume_avg_period']).mean()
    df['vol_ratio']        = df['Volume'] / (df['vol_avg'] + 1e-10)
    df['macd_bull']        = (df['macd'] > df['macd_sig']) & (df['macd'].shift(1) <= df['macd_sig'].shift(1))
    df['below_dma20']      = (df['Close'] < df['dma20']).astype(int)
    df['dma20_days_below'] = df['below_dma20'].rolling(c['dma_exit_days']).sum()

    # ✅ v9: Days stock has been continuously above 50 DMA
    df['above_dma50']      = (df['Close'] > df['dma50']).astype(int)
    df['dma50_days_above'] = df['above_dma50'].rolling(c['dma50_confirm_days']).sum()

    return df


def compute_hybrid_regime(nifty_close):
    """
    ✅ v9: Three-tier hybrid regime.

    Returns a Series of values:
        2 = STRONG UPTREND  (above both 50 DMA and 200 DMA) → full position
        1 = WEAK UPTREND    (above 200 DMA, below 50 DMA)   → half position
        0 = DOWNTREND       (below 200 DMA)                  → no new entries
    """
    dma50  = nifty_close.rolling(CONFIG['regime_fast_dma']).mean()
    dma200 = nifty_close.rolling(CONFIG['regime_slow_dma']).mean()

    regime = pd.Series(0, index=nifty_close.index)
    regime[nifty_close > dma200]                                    = 1  # weak uptrend
    regime[(nifty_close > dma200) & (nifty_close > dma50)]         = 2  # strong uptrend
    return regime


# ================================================================
# DATA DOWNLOAD
# ================================================================

def download_all_data(tickers, start, end):
    print(f"\n⬇️  Downloading {len(tickers)} stocks | {start} → {end}")
    print("    Fast if cached from previous run.\n")
    all_data, failed = {}, []
    batches = [tickers[i:i+20] for i in range(0, len(tickers), 20)]
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}/{len(batches)} ({len(batch)} stocks)...", end=' ', flush=True)
        try:
            raw = yf.download(batch, start=start, end=end,
                              group_by='ticker', auto_adjust=True,
                              progress=False, threads=True)
            for ticker in batch:
                try:
                    df = raw[ticker].copy() if len(batch) > 1 else raw.copy()
                    df = flatten_columns(df)
                    df = df.dropna(subset=['Close'])
                    if len(df) < 150:
                        failed.append(ticker)
                        continue
                    all_data[ticker] = compute_indicators(df)
                except Exception:
                    failed.append(ticker)
            print("✅")
        except Exception as e:
            print(f"❌  {e}")
            failed.extend(batch)
        time.sleep(0.3)
    print(f"\n  ✅ Loaded: {len(all_data)} | ❌ Failed/Skipped: {len(failed)}")
    return all_data


# ================================================================
# SIGNAL LOGIC
# ================================================================

def get_buy_signal(df, idx):
    """
    HARD FILTERS (all must pass):
      1. RSI between 55–70
      2. ADX > 25
      3. Price > 50 DMA
      4. ✅ v9: Stock above 50 DMA for 3+ consecutive days (confirms breakout is real)

    MOMENTUM CONFIRMATION (need 2 of 3):
      A. MACD bullish crossover in last 5 days
      B. Volume surge > 1.5x average
      C. 20-day ROC > 5%
    """
    c   = CONFIG
    row = df.iloc[idx]

    for col in ['rsi', 'adx', 'macd', 'roc', 'dma50', 'vol_ratio', 'dma50_days_above']:
        if pd.isna(row[col]):
            return False, 0

    if not (c['rsi_entry_min'] <= row['rsi'] <= c['rsi_entry_max']):
        return False, 0
    if row['adx'] < c['adx_min']:
        return False, 0
    if row['Close'] <= row['dma50']:
        return False, 0

    # ✅ v9: Stock must have been above 50 DMA for at least 3 days
    if row['dma50_days_above'] < c['dma50_confirm_days']:
        return False, 0

    score    = 0
    lookback = df.iloc[max(0, idx-4): idx+1]
    if lookback['macd_bull'].any():
        score += 1
    if row['vol_ratio'] >= c['volume_surge_min']:
        score += 1
    if row['roc'] >= c['roc_min']:
        score += 1

    return (score >= c['momentum_conditions_min']), score


def check_exit(df, idx, entry_price, entry_date, highest_price):
    """
    EXIT CONDITIONS (priority order):
      1. Profit target: +15%
      2. Trailing stop (activates at +10%, trails -7%, floor at -5%)
      3. Hard stop: -5% (before trailing activates)
      4. Time stop: 65 days
      5. RSI overbought: >78
      6. Below 20 DMA for 3 consecutive days
    """
    c          = CONFIG
    row        = df.iloc[idx]
    cur_date   = df.index[idx]
    cur_price  = float(row['Close'])
    highest_price = max(highest_price, cur_price)

    pct_from_entry = (cur_price - entry_price) / entry_price
    pct_peak       = (highest_price - entry_price) / entry_price

    if pct_from_entry >= c['profit_target_pct']:
        return True, f"Profit Target (+{pct_from_entry*100:.1f}%)", highest_price

    if pct_peak >= c['trailing_activation_pct']:
        effective_stop = max(highest_price * (1 - c['trailing_stop_pct']),
                             entry_price * (1 - c['stop_loss_pct']))
        if cur_price <= effective_stop:
            return True, f"Trailing Stop ({pct_from_entry*100:+.1f}%)", highest_price
    else:
        if pct_from_entry <= -c['stop_loss_pct']:
            return True, f"Stop Loss ({pct_from_entry*100:.1f}%)", highest_price

    if (cur_date - entry_date).days >= c['max_hold_days']:
        return True, f"Time Stop ({(cur_date-entry_date).days}d, {pct_from_entry*100:+.1f}%)", highest_price

    if not pd.isna(row['rsi']) and row['rsi'] > c['rsi_exit']:
        return True, f"RSI Overbought ({row['rsi']:.1f})", highest_price

    if not pd.isna(row['dma20_days_below']) and row['dma20_days_below'] >= c['dma_exit_days']:
        return True, f"Below 20 DMA ({c['dma_exit_days']} days)", highest_price

    return False, "", highest_price


# ================================================================
# BACKTEST ENGINE
# ================================================================

def run_backtest(all_data, nifty_close):
    c = CONFIG
    print("\n🔄 Running backtest simulation...\n")

    trading_days = nifty_close.index.tolist()
    regime       = compute_hybrid_regime(nifty_close)

    strong  = int((regime == 2).sum())
    weak    = int((regime == 1).sum())
    down    = int((regime == 0).sum())
    total   = len(trading_days)

    print(f"  Trading days      : {total}")
    print(f"  Stocks loaded     : {len(all_data)}")
    print(f"  📈 Strong Uptrend : {strong} days ({strong/total*100:.0f}%) → FULL position size")
    print(f"  〰️  Weak Uptrend  : {weak} days ({weak/total*100:.0f}%) → HALF position size")
    print(f"  📉 Downtrend      : {down} days ({down/total*100:.0f}%) → NO new entries\n")

    cash           = float(c['initial_capital'])
    portfolio      = {}
    completed      = []
    daily_val      = []
    regime_blocked = 0
    half_size_days = 0

    for day_num, date in enumerate(trading_days):
        if day_num % 250 == 0:
            pv = cash + sum(
                pos['shares'] * float(all_data[t].loc[date, 'Close'])
                for t, pos in portfolio.items()
                if all_data.get(t) is not None and date in all_data[t].index
            )
            r = regime.get(date, 2)
            mkt = "📈 STRONG" if r == 2 else ("〰️  WEAK" if r == 1 else "📉 DOWN")
            print(f"  📅 {date.date()}  {mkt}  |  ₹{pv:,.0f}  |  Cash: ₹{cash:,.0f}  |  Pos: {len(portfolio)}")

        # ── STEP 1: Exits ─────────────────────────────────────────
        to_exit = []
        for ticker, pos in portfolio.items():
            df = all_data.get(ticker)
            if df is None or date not in df.index:
                continue
            idx = df.index.get_loc(date)
            should_exit, reason, new_high = check_exit(
                df, idx, pos['entry_price'], pos['entry_date'], pos['highest_price']
            )
            portfolio[ticker]['highest_price'] = new_high
            if should_exit:
                exit_price = float(df.loc[date, 'Close'])
                proceeds   = pos['shares'] * exit_price * (1 - c['cost_per_side'])
                pnl_pct    = (exit_price / pos['entry_price'] - 1) * 100 - c['cost_per_side'] * 100
                cash      += proceeds
                completed.append({
                    'ticker'       : ticker,
                    'entry_date'   : pos['entry_date'],
                    'exit_date'    : date,
                    'entry_price'  : round(pos['entry_price'], 2),
                    'exit_price'   : round(exit_price, 2),
                    'highest_price': round(new_high, 2),
                    'hold_days'    : (date - pos['entry_date']).days,
                    'pct_return'   : round(pnl_pct, 2),
                    'pnl_inr'      : round(proceeds - pos['invested'], 2),
                    'exit_reason'  : reason,
                    'score'        : pos.get('score', 0),
                    'regime_entry' : pos.get('regime_entry', 'Unknown'),
                })
                to_exit.append(ticker)
        for t in to_exit:
            del portfolio[t]

        # ── STEP 2: Entries (regime-gated + sized) ────────────────
        r = int(regime.get(date, 2))

        if r == 0:
            regime_blocked += 1
        else:
            free_slots = c['max_portfolio_size'] - len(portfolio)
            if free_slots > 0 and cash > 1000:
                candidates = []
                for ticker, df in all_data.items():
                    if ticker in portfolio or date not in df.index:
                        continue
                    idx = df.index.get_loc(date)
                    if idx + 1 >= len(df):
                        continue
                    is_buy, score = get_buy_signal(df, idx)
                    if is_buy:
                        candidates.append((ticker, score, df, idx))

                candidates.sort(key=lambda x: x[1], reverse=True)

                for ticker, score, df, idx in candidates[:free_slots]:
                    next_row    = df.iloc[idx + 1]
                    entry_price = float(next_row['Open'])
                    if pd.isna(entry_price) or entry_price <= 0:
                        continue

                    # ✅ v9: Scale position size by regime
                    # Strong uptrend (r=2): full 1/5 of cash
                    # Weak uptrend (r=1): half of that
                    size_multiplier = 1.0 if r == 2 else c['half_size_pct']
                    base_alloc = cash / free_slots
                    alloc      = base_alloc * size_multiplier
                    cost       = alloc * (1 + c['cost_per_side'])
                    if cost > cash:
                        alloc = cash / (1 + c['cost_per_side'])
                        cost  = cash
                    if alloc < 100:
                        continue

                    if r == 1:
                        half_size_days += 1

                    shares = alloc / entry_price
                    cash  -= cost
                    portfolio[ticker] = {
                        'entry_price'  : entry_price,
                        'entry_date'   : df.index[idx + 1],
                        'shares'       : shares,
                        'invested'     : alloc,
                        'score'        : score,
                        'highest_price': entry_price,
                        'regime_entry' : 'Strong' if r == 2 else 'Weak',
                    }
                    free_slots -= 1
                    if free_slots <= 0 or cash < 100:
                        break

        # ── STEP 3: End-of-day value ──────────────────────────────
        holdings_value = sum(
            pos['shares'] * float(all_data[t].loc[date, 'Close'])
            for t, pos in portfolio.items()
            if all_data.get(t) is not None and date in all_data[t].index
        )
        daily_val.append({
            'date'       : date,
            'value'      : cash + holdings_value,
            'cash'       : cash,
            'holdings'   : holdings_value,
            'n_positions': len(portfolio),
            'regime'     : r,
        })

    # Close remaining positions
    for ticker, pos in portfolio.items():
        df = all_data.get(ticker)
        if df is None:
            continue
        exit_price = float(df.iloc[-1]['Close'])
        proceeds   = pos['shares'] * exit_price * (1 - c['cost_per_side'])
        pnl_pct    = (exit_price / pos['entry_price'] - 1) * 100 - c['cost_per_side'] * 100
        completed.append({
            'ticker'       : ticker,
            'entry_date'   : pos['entry_date'],
            'exit_date'    : df.index[-1],
            'entry_price'  : round(pos['entry_price'], 2),
            'exit_price'   : round(exit_price, 2),
            'highest_price': round(pos['highest_price'], 2),
            'hold_days'    : (df.index[-1] - pos['entry_date']).days,
            'pct_return'   : round(pnl_pct, 2),
            'pnl_inr'      : round(proceeds - pos['invested'], 2),
            'exit_reason'  : 'End of Backtest',
            'score'        : pos.get('score', 0),
            'regime_entry' : pos.get('regime_entry', 'Unknown'),
        })

    print(f"\n  🚦 Downtrend blocked  : {regime_blocked} days ({regime_blocked/total*100:.0f}%)")
    print(f"  〰️  Half-size entries : {half_size_days} entries in weak uptrend")

    return completed, pd.DataFrame(daily_val).set_index('date')


# ================================================================
# RESULTS
# ================================================================

def print_results(completed, daily_df, nifty_close):
    c = CONFIG
    if not completed:
        print("\n❌ No trades completed.")
        return

    trades  = pd.DataFrame(completed)
    n_years = (daily_df.index[-1] - daily_df.index[0]).days / 365.25

    start_val = float(c['initial_capital'])
    end_val   = float(daily_df['value'].iloc[-1])
    total_ret = (end_val - start_val) / start_val * 100
    cagr      = ((end_val / start_val) ** (1 / n_years) - 1) * 100
    daily_ret = daily_df['value'].pct_change().dropna()
    sharpe    = (daily_ret.mean() / (daily_ret.std() + 1e-10)) * np.sqrt(252)
    rolling_max = daily_df['value'].cummax()
    max_dd      = ((daily_df['value'] - rolling_max) / rolling_max).min() * 100

    nifty_s     = nifty_close.squeeze()
    nifty_start = float(nifty_s.iloc[0])
    nifty_end   = float(nifty_s.iloc[-1])
    nifty_ret   = (nifty_end - nifty_start) / nifty_start * 100
    nifty_cagr  = ((nifty_end / nifty_start) ** (1 / n_years) - 1) * 100

    winners  = trades[trades['pct_return'] > 0]
    losers   = trades[trades['pct_return'] <= 0]
    win_rate = len(winners) / len(trades) * 100 if len(trades) else 0
    avg_win  = winners['pct_return'].mean() if len(winners) else 0
    avg_loss = losers['pct_return'].mean()  if len(losers)  else 0
    expect   = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)

    print("\n" + "═"*62)
    print("                  📊 BACKTEST RESULTS  v9")
    print("═"*62)
    print(f"\n  🏦 Starting Capital   : ₹{start_val:>12,.0f}")
    print(f"  💰 Ending Capital     : ₹{end_val:>12,.0f}")
    print(f"  📈 Total Return       :  {total_ret:>+8.1f}%")
    print(f"  🚀 CAGR               :  {cagr:>+8.1f}%")
    print(f"  📊 Sharpe Ratio       :  {sharpe:>8.2f}")
    print(f"  📉 Max Drawdown       :  {max_dd:>8.1f}%")
    print(f"  ⏱️  Period              :  {n_years:.1f} years")
    print(f"\n  {'─'*38}")
    print(f"  🏁 Nifty 50 Return    :  {nifty_ret:>+8.1f}%")
    print(f"  🏁 Nifty 50 CAGR      :  {nifty_cagr:>+8.1f}%")
    print(f"  🎯 Alpha (vs Nifty)   :  {cagr - nifty_cagr:>+8.1f}%")

    print(f"\n  {'─'*38}")
    print(f"  📋 Total Trades       : {len(trades)}")
    print(f"  ✅ Win Rate           : {win_rate:.1f}%")
    print(f"  🟢 Winners / 🔴 Losers: {len(winners)} / {len(losers)}")
    print(f"  📈 Avg Winner         : +{avg_win:.2f}%")
    print(f"  📉 Avg Loser          : {avg_loss:.2f}%")
    print(f"  💡 Expectancy/trade   : {expect:+.2f}%")
    print(f"  ⏳ Avg Hold Duration  : {trades['hold_days'].mean():.0f} days")

    # Stop loss rate specifically
    sl_trades = trades[trades['exit_reason'].str.startswith('Stop Loss')]
    print(f"  🛑 Stop Loss rate     : {len(sl_trades)/len(trades)*100:.1f}% ({len(sl_trades)} trades)")

    best  = trades.loc[trades['pct_return'].idxmax()]
    worst = trades.loc[trades['pct_return'].idxmin()]
    print(f"\n  🏆 Best  : {best['ticker']:>15}  {best['pct_return']:>+7.1f}%  ({int(best['hold_days'])} days)")
    print(f"  💀 Worst : {worst['ticker']:>15}  {worst['pct_return']:>+7.1f}%  ({int(worst['hold_days'])} days)")

    # Regime performance
    if 'regime_entry' in trades.columns:
        print(f"\n  {'─'*38}")
        print(f"  🔍 PERFORMANCE BY REGIME AT ENTRY")
        for regime_type in ['Strong', 'Weak']:
            r_trades = trades[trades['regime_entry'] == regime_type]
            if len(r_trades) > 0:
                r_win  = (r_trades['pct_return'] > 0).sum()
                r_avg  = r_trades['pct_return'].mean()
                print(f"    {regime_type} Uptrend : {len(r_trades)} trades, "
                      f"Win {r_win/len(r_trades)*100:.0f}%, Avg {r_avg:+.2f}%")

    # Exit reasons
    trades['exit_group'] = trades['exit_reason'].apply(
        lambda x: 'Profit Target'  if x.startswith('Profit')    else
                  'Trailing Stop'  if x.startswith('Trailing')   else
                  'Stop Loss'      if x.startswith('Stop Loss')  else
                  'Time Stop'      if x.startswith('Time')       else
                  'RSI Overbought' if x.startswith('RSI')        else
                  'Below 20 DMA'   if x.startswith('Below')      else x
    )
    print(f"\n  {'─'*38}")
    print(f"  🚪 EXIT REASONS                   trades    %     avg return")
    for reason, cnt in trades['exit_group'].value_counts().items():
        avg_ret = trades[trades['exit_group'] == reason]['pct_return'].mean()
        bar     = '█' * int(cnt / len(trades) * 25)
        print(f"    {reason:<20} {cnt:>4}  ({cnt/len(trades)*100:>4.1f}%)  {avg_ret:>+6.1f}%  {bar}")

    # Trailing stop detail
    trail = trades[trades['exit_group'] == 'Trailing Stop']
    if len(trail) > 0:
        t_win = trail[trail['pct_return'] > 0]
        t_los = trail[trail['pct_return'] <= 0]
        print(f"\n    ↳ Trailing Stop breakdown:")
        if len(t_win): print(f"      Profitable : {len(t_win)} ({len(t_win)/len(trail)*100:.0f}%)  avg: +{t_win['pct_return'].mean():.1f}%")
        if len(t_los): print(f"      At loss    : {len(t_los)} ({len(t_los)/len(trail)*100:.0f}%)  avg: {t_los['pct_return'].mean():.1f}%")

    # Year by year
    print(f"\n  {'─'*38}")
    print(f"  📅 YEAR-BY-YEAR PERFORMANCE")
    daily_df['year']     = daily_df.index.year
    yearly               = daily_df.groupby('year')['value'].agg(['first','last'])
    yearly['return']     = (yearly['last'] / yearly['first'] - 1) * 100
    nifty_df             = pd.DataFrame({'close': nifty_s})
    nifty_df['year']     = nifty_df.index.year
    nifty_yrly           = nifty_df.groupby('year')['close'].agg(['first','last'])
    nifty_yrly['return'] = (nifty_yrly['last'] / nifty_yrly['first'] - 1) * 100
    beats = 0
    print(f"    {'Year':<6} {'Strategy':>10} {'Nifty50':>10} {'Alpha':>10}")
    print(f"    {'─'*42}")
    for year in sorted(yearly.index):
        s = yearly.loc[year, 'return']
        n = nifty_yrly.loc[year, 'return'] if year in nifty_yrly.index else 0
        flag = '✅' if s > n else '❌'
        if s > n: beats += 1
        print(f"    {year:<6} {s:>+9.1f}%  {n:>+9.1f}%  {s-n:>+9.1f}%  {flag}")
    total_years = len(yearly)
    print(f"\n    Beat Nifty in {beats}/{total_years} years ({beats/total_years*100:.0f}%)")

    # Top 10
    print(f"\n  {'─'*38}")
    print(f"  🔝 TOP 10 TRADES BY RETURN")
    top = trades.nlargest(10, 'pct_return')[
        ['ticker','entry_date','exit_date','pct_return','hold_days','exit_reason']
    ].copy()
    top['entry_date'] = pd.to_datetime(top['entry_date']).dt.strftime('%Y-%m-%d')
    top['exit_date']  = pd.to_datetime(top['exit_date']).dt.strftime('%Y-%m-%d')
    print(top.to_string(index=False))

    # Diagnostic
    wl = avg_win / abs(avg_loss) if avg_loss != 0 else 0
    print(f"\n  {'─'*38}")
    print(f"  🔬 DIAGNOSTIC SUMMARY")
    print(f"    Expectancy/trade : {expect:+.2f}%  {'✅' if expect > 0 else '❌'}")
    print(f"    Win:Loss ratio   : {avg_win:.2f}/{abs(avg_loss):.2f} = {wl:.2f}x  {'✅' if wl >= 1.5 else '⚠️'}")
    print(f"    Stop loss rate   : {len(sl_trades)/len(trades)*100:.1f}%  {'✅ Improved' if len(sl_trades)/len(trades) < 0.35 else '⚠️ Still high'}")
    print(f"    Max Drawdown     : {max_dd:.1f}%  {'✅ Controlled' if max_dd > -30 else '⚠️ Still high'}")
    print(f"    Beat Nifty years : {beats}/{total_years} ({beats/total_years*100:.0f}%)")
    print(f"    CAGR vs Nifty    : {cagr:.1f}% vs {nifty_cagr:.1f}%")
    if cagr > nifty_cagr:
        print(f"    🎉 STRATEGY BEATS NIFTY by {cagr-nifty_cagr:.1f}% CAGR!")
    else:
        print(f"    ❌ {nifty_cagr-cagr:.1f}% below Nifty CAGR — closing the gap")

    print("\n" + "═"*62 + "\n")
    trades.to_csv('trade_log.csv', index=False)
    daily_df.to_csv('portfolio_value.csv')
    print("  💾 Saved: trade_log.csv  +  portfolio_value.csv\n")


# ================================================================
# MAIN
# ================================================================

if __name__ == '__main__':
    print("\n" + "═"*62)
    print("   🚀 MOMENTUM SWING TRADING BACKTEST  v9")
    print("      Nifty 500  |  India  |  5-Stock Portfolio")
    print("═"*62)
    print(f"\n  v9 Changes:")
    print(f"    ✅ Hybrid regime : Strong (above 50+200 DMA) → full size")
    print(f"                       Weak   (above 200, below 50) → half size")
    print(f"                       Down   (below 200 DMA)  → no entries")
    print(f"    ✅ Stock above 50 DMA for {CONFIG['dma50_confirm_days']}+ days before entry")

    universe = get_universe()
    print(f"\n📋 Universe: {len(universe)} stocks")

    print("\n⬇️  Downloading Nifty 50 benchmark...")
    raw_nifty   = yf.download('^NSEI', start=CONFIG['start_date'],
                               end=CONFIG['end_date'], auto_adjust=True, progress=False)
    raw_nifty   = flatten_columns(raw_nifty)
    nifty_close = raw_nifty['Close'].squeeze()

    all_data = download_all_data(universe, CONFIG['start_date'], CONFIG['end_date'])
    if not all_data:
        print("❌ No data downloaded.")
        sys.exit(1)

    completed, daily_df = run_backtest(all_data, nifty_close)
    print_results(completed, daily_df, nifty_close)