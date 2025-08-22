import requests
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
import pytz

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = '8490094419:AAEQZNSe4JzxDRowNyscVHyjjz4clOfnp2k'
TELEGRAM_CHAT_ID = '555707299'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram send error: {e}")

# --- GET SINGAPORE TIME ---
def get_singapore_time():
    tz = pytz.timezone("Asia/Singapore")
    sg_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    return sg_time

# --- READ SYMBOLS FROM TXT ---
def load_symbol_list(filename="future_usdt_usdm_pairs.txt"):
    try:
        with open(filename, "r") as file:
            symbols = [line.strip().upper() for line in file if line.strip()]
        return symbols
    except Exception as e:
        print(f"❌ Error reading symbol list: {e}")
        return []

# --- GET CANDLE DATA FROM BINANCE FUTURES ---
def get_klines(symbol, interval="15m", limit=20):
    url = f"https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'num_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

# --- 24H VOLUME DATA ---
def get_24h_stats(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
        res = requests.get(url).json()
        return float(res["quoteVolume"])
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return None

# --- CHECK STRATEGY CONDITIONS ---
def check_conditions(symbol):
    df = get_klines(symbol, interval="15m", limit=20)
    if len(df) < 4:
        print(f"⛔ {symbol} - Not enough candles")
        return None

    # Candles
    prev2 = df.iloc[-3]
    prev1 = df.iloc[-2]
    curr = df.iloc[-1]

    if curr['close'] <= curr['open']:
        print(f"❌ {symbol} - Current candle is not green")
        return None

    # 4 EMA condition
    df['ema_4'] = ta.ema(df['close'], length=4)
    ema_4 = df['ema_4'].iloc[-1]
    if pd.isna(ema_4):
        print(f"⚠️ {symbol} - EMA could not be calculated")
        return None

    if not (prev1['low'] < curr['low'] and prev1['low'] < prev2['low']):
        print(f"❌ {symbol} - Prev1 low not lower than curr & prev2")
        return None

    if prev1['close'] > prev1['open']:  # prev1 green
        if curr['close'] <= prev1['open']:
            print(f"❌ {symbol} - Prev1 is green, curr close not above prev1 open")
            return None
    elif prev1['close'] < prev1['open']:  # prev1 red
        if curr['close'] <= prev1['close']:
            print(f"❌ {symbol} - Prev1 is red, curr close not above prev1 close")
            return None
        
    if curr['close'] < ema_4 and curr['high'] < ema_4:
        print(f"❌ {symbol} - Close and High below 4 EMA (Close: {curr['close']:.2f}, High: {curr['high']:.2f}, EMA: {ema_4:.2f})")
        return None
    
    # RSI
    df['rsi'] = ta.rsi(df['close'], length=14)
    current_rsi = df['rsi'].iloc[-1]
    if pd.isna(current_rsi):
        print(f"⚠️ {symbol} - RSI could not be calculated")
        return None
    if current_rsi >= 50:
        print(f"❌ {symbol} - RSI >= 50 ({current_rsi:.2f})")
        return None
    if current_rsi < 30:
        print(f"❌ {symbol} - RSI < 30 ({current_rsi:.2f})")
        return None

    # Volume
    volume_24h = get_24h_stats(symbol)
    if volume_24h is None or volume_24h < 20_000_000:
        print(f"❌ {symbol} - Volume < $20M ({volume_24h})")
        return None

    print(f"✅ {symbol} passed all checks")
    return {
        "symbol": symbol,
        "rsi": round(current_rsi, 2),
        "price": round(curr['close'], 4),
        "volume": round(volume_24h),
        "sg_time": get_singapore_time()
    }

# --- MAIN EXECUTION ---
def run_strategy():
    print("🔍 Starting 15-min Futures Signal Screener...\n")
    start_time = time.time()

    target_symbols = load_symbol_list("future_usdt_usdm_pairs.txt")
    if not target_symbols:
        print("❌ No symbols loaded from txt.")
        return

    total = 0
    signals_sent = 0

    for symbol in target_symbols:
        if not symbol.endswith("USDT"):
            continue

        total += 1
        print(f"\n🔁 Checking {symbol}")
        try:
            result = check_conditions(symbol)
            if result:
                msg = (
                    f"🔥Future USDT 15m Signal\n"
                    f"Symbol: {result['symbol']}\n"
                    f"RSI: {result['rsi']}\n"
                    f"Price: {result['price']}\n"
                    f"24h Volume: {result['volume']}\n"
                    f"Date/Time (SGT): {result['sg_time']}"
                )
                send_telegram_message(msg)
                signals_sent += 1
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
        time.sleep(0.1)

    duration = time.time() - start_time
    print(f"\n✅ Done.\n🔢 Total Symbols: {total}\n📤 Signals Sent: {signals_sent}\n⏱️ Time: {duration:.2f} sec")

    summary = (
        f"✅ 15m Futures Scan Complete\n"
        f"Total Symbols: {total}\n"
        f"Signals Sent: {signals_sent}\n"
        f"Time: {duration:.2f} sec"
    )
    send_telegram_message(summary)

# --- START ---
if __name__ == "__main__":
    run_strategy()
