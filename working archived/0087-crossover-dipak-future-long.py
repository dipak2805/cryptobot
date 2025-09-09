import requests
import pandas as pd
import numpy as np
import pandas_ta as ta
import time
from datetime import datetime
import pytz

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
SYMBOLS_FILE = "future_usdt_usdm_pairs.txt"

INTERVAL = "1h"      # 1h/4h/15m/5m
LIMIT = 300           # more candles to compute indicators safely
LOOKBACK_CROSS = 80   # bars to look back for last EMA cross event
SLEEP_BETWEEN_SYMBOLS = 0.12  # polite delay between requests

# RSI & logic thresholds (match Pine defaults)
RSI_LENGTH = 25
RSI_BUY = 55
RSI_SELL = 45  # not used here (long-only)
CI_LEN = 14
CI_MID = 45
VOL_SMA = 14
LOWAVG_LEN = 14
HIGHAVG_LEN = 14
EMA_FAST = 8
EMA_SLOW = 14
CMF_LEN = 25

# =========================
# UTIL
# =========================
def ist_time_str():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def sgt_time_str():
    tz = pytz.timezone("Asia/Singapore")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[TG] error: {e}")

def load_symbols(path=SYMBOLS_FILE):
    try:
        with open(path, "r") as f:
            syms = [line.strip().upper() for line in f if line.strip()]
        # keep only USDT-margined futures symbols
        return [s for s in syms if s.endswith("USDT")]
    except Exception as e:
        print(f"❌ Error reading symbols: {e}")
        return []

def get_klines(symbol, interval=INTERVAL, limit=LIMIT) -> pd.DataFrame:
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return pd.DataFrame()
        cols = ['open_time','open','high','low','close','volume',
                'close_time','qav','num_trades','tbbav','tbqav','ignore']
        df = pd.DataFrame(data, columns=cols)
        for c in ['open','high','low','close','volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df.dropna(inplace=True)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        return df
    except Exception as e:
        print(f"❌ {symbol} klines error: {e}")
        return pd.DataFrame()

# =========================
# INDICATORS (mirror Pine logic)
# =========================
def choppiness_index(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """
    CI = 100 * log10(sum(ATR(1), n) / (highest(high, n) - lowest(low, n))) / log10(n)
    """
    if len(df) < length + 2:
        return pd.Series([np.nan] * len(df), index=df.index)

    atr1 = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=1)
    atr_sum = atr1.rolling(length).sum()
    highest_high = df['high'].rolling(length).max()
    lowest_low = df['low'].rolling(length).min()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    ci = 100 * np.log10(atr_sum / denom) / np.log10(length)
    return ci

def last_cross_event_idx(fast: pd.Series, slow: pd.Series, lookback: int):
    """
    Find index (offset from end) and type of last EMA cross within lookback window.
    Returns (kind, idx_from_end)
      kind: "bullish" if fast crossed above slow; "bearish" if crossed below; None if none
    """
    # compute difference
    diff = fast - slow
    sign = np.sign(diff)
    # A crossover occurs where sign changes
    cross_idx = np.where(np.diff(sign) != 0)[0]  # indices BEFORE the change
    if cross_idx.size == 0:
        return None, None
    last_idx = cross_idx[-1]
    # Limit to lookback
    # convert to "bars from end": (len-2) - last_idx because diff reduces 1 length
    bars_from_end = (len(fast) - 2) - last_idx
    if bars_from_end > lookback:
        return None, None
    # Determine type using the two points around crossover
    before = diff.iloc[last_idx]
    after = diff.iloc[last_idx + 1]
    if before < 0 and after > 0:
        return "bullish", bars_from_end
    elif before > 0 and after < 0:
        return "bearish", bars_from_end
    else:
        return None, None

# =========================
# SIGNAL LOGIC (Long-only)
# =========================
def compute_signals(symbol: str):
    df = get_klines(symbol)
    if df.empty or len(df) < 60:
        return None

    # EMAs
    df['ema_fast'] = ta.ema(df['close'], length=EMA_FAST)
    df['ema_slow'] = ta.ema(df['close'], length=EMA_SLOW)

    # RSI
    df['rsi'] = ta.rsi(df['close'], length=RSI_LENGTH)

    # Choppiness Index
    df['ci'] = choppiness_index(df, length=CI_LEN)

    # Volume SMA
    df['vol_sma'] = ta.sma(df['volume'], length=VOL_SMA)

    # High/Low averages
    df['lowAvg'] = ta.sma(df['low'], length=LOWAVG_LEN)
    df['highAvg'] = ta.sma(df['high'], length=HIGHAVG_LEN)

    # CMF
    # pandas_ta.cmf uses hlc3 & volume – equivalent to Pine's CMF
    df['cmf'] = ta.cmf(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], length=CMF_LEN)

    # Candle strength
    mid = (df['high'] + df['low']) / 2.0
    df['bullish_candle'] = (df['close'] > df['open']) & (df['close'] >= mid)
    df['bearish_candle'] = (df['close'] < df['open']) & (df['close'] <= mid)

    # Price touching EMAs (for add-position)
    df['touch_ema8_low'] = df['low'] <= df['ema_fast']

    # Volume condition
    df['vol_ok'] = df['volume'] > df['vol_sma']

    # Determine last cross event within window (approx for Pine persistent flags)
    cross_kind, bars_from_end = last_cross_event_idx(df['ema_fast'], df['ema_slow'], LOOKBACK_CROSS)

    # Use last complete candle (avoid partial bar)
    last = df.iloc[-1]

    # BUY (Daily) signal:
    #  - Last cross event must be bullish (crossover happened)
    #  - CI < 50 (trending)
    #  - RSI >= 55
    #  - Volume > avg
    #  - Bullish candle
    buy_signal = (
        (cross_kind == "bullish") &
        (last['ci'] < CI_MID) &
        (last['rsi'] >= RSI_BUY) &
        (last['vol_ok'] == True) &
        (last['bullish_candle'] == True)
    )

    # ADD POSITION signal:
    #  - Last cross event bullish (we're in bullish regime)
    #  - Low touches EMA8
    #  - RSI >= 55
    #  - Bullish candle
    add_pos_signal = (
        (cross_kind == "bullish") &
        (last['touch_ema8_low'] == True) &
        (last['rsi'] >= RSI_BUY) &
        (last['bullish_candle'] == True) &
        (last['ci'] < CI_MID) 
    )

    # BUY ON DIPS:
    #  - Bullish candle AND close > lowAvg AND open <= lowAvg
    buy_on_dips_signal = (
        (last['bullish_candle'] == True) &
        (last['close'] > last['lowAvg']) &
        (last['open'] <= last['lowAvg']) &
        (last['ci'] < CI_MID) 
    )

    # CMF dip assist (optional): between -0.05 and 0.10 and showing upward momentum
    # Can be used to strengthen Buy on Dips (left as info)
    cmf_val = float(last['cmf']) if pd.notna(last['cmf']) else None

    results = {
        "symbol": symbol,
        "price": float(last['close']),
        "time_ist": ist_time_str(),
        "time_sgt": sgt_time_str(),   # NEW
        "buy": bool(buy_signal),
        "add_pos": bool(add_pos_signal),
        "buy_on_dips": bool(buy_on_dips_signal),
        "ci": float(last['ci']) if pd.notna(last['ci']) else None,
        "rsi": float(last['rsi']) if pd.notna(last['rsi']) else None,
        "cmf": cmf_val
    }
    return results

def format_signal_message(res):
    lines = [f"✅ Futures LONG Signal ({INTERVAL})",
             f"Symbol: {res['symbol']}",
             f"Price: {res['price']:.6f}",
             f"Time (IST): {res['time_ist']}",
             f"Time (SGT): {res['time_sgt']}"]   # NEW
    tags = []
    if res['buy']:
        tags.append("Buy(Daily)")
    if res['add_pos']:
        tags.append("Add Position")
    if res['buy_on_dips']:
        tags.append("Buy on Dips")
    if tags:
        lines.append(f"Type: {', '.join(tags)}")
    if res['rsi'] is not None:
        lines.append(f"RSI({RSI_LENGTH}): {res['rsi']:.2f}")
    if res['ci'] is not None:
        lines.append(f"CI({CI_LEN}): {res['ci']:.2f}")  # already in place ✅
    if res['cmf'] is not None:
        lines.append(f"CMF({CMF_LEN}): {res['cmf']:.4f}")
    return "\n".join(lines)

# =========================
# MAIN
# =========================
def run():
    symbols = load_symbols()
    if not symbols:
        print("❌ No symbols found in file.")
        return

    print(f"🔍 Scanning {len(symbols)} symbols on {INTERVAL} ...")
    total = 0
    signals = 0
    fired = []

    for sym in symbols:
        total += 1
        try:
            res = compute_signals(sym)
            if not res:
                print(f"⚠️ {sym}: insufficient data")
            else:
                if res['buy'] or res['add_pos'] or res['buy_on_dips']:
                    msg = format_signal_message(res)
                    print(msg)
                    send_telegram(msg)
                    signals += 1
                    fired.append(sym)
                else:
                    print(f"— {sym}: no long signals")
        except Exception as e:
            print(f"❌ {sym} error: {e}")
        time.sleep(SLEEP_BETWEEN_SYMBOLS)

    # optional: write triggered symbols
    try:
        with open("future_usdt_long_signals.txt", "w") as f:
            for s in fired:
                f.write(s + "\n")
    except Exception as e:
        print(f"File write error: {e}")

    summary = (f"✅ Futures LONG Scan Complete ({INTERVAL})\n"
               f"Total Symbols: {total}\n"
               f"Signals Sent: {signals}\n"
               f"Time (IST): {ist_time_str()}")
    print(summary)
    send_telegram(summary)

if __name__ == "__main__":
    run()