import requests
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
import pytz

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = 'your_token_here'
TELEGRAM_CHAT_ID = 'your_chat_id_here'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram send error: {e}")

def get_singapore_time():
    tz = pytz.timezone("Asia/Singapore")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def load_symbol_list(filename="future_usdt_usdm_pairs.txt"):
    try:
        with open(filename, "r") as file:
            symbols = [line.strip().upper() for line in file if line.strip()]
        return symbols
    except Exception as e:
        print(f"❌ Error reading symbol list: {e}")
        return []

def get_klines(symbol, interval="1h", limit=50):
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
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

def get_24h_stats(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
        res = requests.get(url).json()
        return float(res["quoteVolume"])
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return None

def check_conditions(symbol):
    # --- 1H data (primary cross check) ---
    df_1h = get_klines(symbol, interval="1h", limit=30)
    if df_1h.empty:
        return None

    df_1h['sma7'] = ta.sma(df_1h['close'], length=7)
    df_1h['sma25'] = ta.sma(df_1h['close'], length=25)

    if len(df_1h) < 26:
        print(f"⛔ {symbol} - Not enough 1H candles for SMA check")
        return None

    prev_sma7 = df_1h['sma7'].iloc[-2]
    prev_sma25 = df_1h['sma25'].iloc[-2]
    curr_sma7 = df_1h['sma7'].iloc[-1]
    curr_sma25 = df_1h['sma25'].iloc[-1]

    # Bearish cross check on 1H
    if not (prev_sma7 > prev_sma25 and curr_sma7 < curr_sma25):
        print(f"❌ {symbol} - No bearish SMA cross on 1H")
        return None

    # --- 15m data (confirmation check) ---
    df_15m = get_klines(symbol, interval="15m", limit=30)
    if df_15m.empty:
        return None

    df_15m['sma7'] = ta.sma(df_15m['close'], length=7)
    df_15m['sma25'] = ta.sma(df_15m['close'], length=25)

    curr_sma7_15m = df_15m['sma7'].iloc[-1]
    curr_sma25_15m = df_15m['sma25'].iloc[-1]

    if not (curr_sma7_15m < curr_sma25_15m):
        print(f"❌ {symbol} - SMA7 not below SMA25 on 15m")
        return None

    # --- Volume check ---
    volume_24h = get_24h_stats(symbol)
    if volume_24h is None or volume_24h < 20_000_000:
        print(f"❌ {symbol} - Volume < $20M ({volume_24h})")
        return None

    print(f"✅ {symbol} passed all checks for short")
    return {
        "symbol": symbol,
        "price": round(df_1h['close'].iloc[-1], 4),
        "volume": round(volume_24h),
        "sg_time": get_singapore_time()
    }

def run_strategy():
    print("🔍 Starting 1H + 15m SMA Bearish Cross Screener...\n")
    start_time = time.time()

    target_symbols = load_symbol_list("future_usdt_usdm_pairs.txt")
    if not target_symbols:
        print("❌ No symbols loaded from txt.")
        return

    total = 0
    signals_sent = 0
    valid_signals = []

    for symbol in target_symbols:
        if not symbol.endswith("USDT"):
            continue

        total += 1
        print(f"\n🔁 Checking {symbol}")
        try:
            result = check_conditions(symbol)
            if result:
                send_telegram_message(f"🚨 1H+15m Short Signal: {result['symbol']} | Price: {result['price']}")
                valid_signals.append(result['symbol'])
                signals_sent += 1
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
        time.sleep(0.1)

    # Write results to file
    with open("future_usdt_1h15m_short_signal.txt", "w") as f:
        for sym in valid_signals:
            f.write(sym + "\n")

    duration = time.time() - start_time
    print(f"\n✅ Done.\n🔢 Total Symbols: {total}\n📤 Signals Sent: {signals_sent}\n⏱️ Time: {duration:.2f} sec")

    summary = (
        f"🚨 1H + 15m SMA Bearish Cross Scan Complete\n"
        f"Total Symbols: {total}\n"
        f"Signals Sent: {signals_sent}\n"
        f"Time: {duration:.2f} sec"
    )
    send_telegram_message(summary)

if __name__ == "__main__":
    run_strategy()
