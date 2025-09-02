import requests
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
import pytz

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

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
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

# --- GET INDIAN TIME ---
def get_indian_time():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

# --- READ SYMBOLS FROM TXT ---
def load_symbol_list(filename="future_usdt_usdm_pairs.txt"):
    try:
        with open(filename, "r") as file:
            symbols = [line.strip().upper() for line in file if line.strip()]
        return symbols
    except Exception as e:
        print(f"❌ Error reading symbol list: {e}")
        return []

# --- GET CANDLE DATA FROM FUTURES ---
def get_klines(symbol, interval="15m", limit=100):
    url = "https://fapi.binance.com/fapi/v1/klines"
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

# --- 24H STATS FROM FUTURES ---
def get_24h_stats(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
        res = requests.get(url).json()
        return float(res["quoteVolume"])
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return None

# --- STRATEGY CHECK ---
def check_conditions(symbol):
    # Get 15m, 1h, 4h data
    df_15m = get_klines(symbol, interval="15m", limit=100)
    df_1h = get_klines(symbol, interval="1h", limit=100)
    df_4h = get_klines(symbol, interval="4h", limit=100)

    if df_15m.empty or df_1h.empty or df_4h.empty:
        return None, f"⚠️ {symbol} - Missing candles"

    # Apply DMI/ADX
    dmi_15m = ta.adx(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
    dmi_1h = ta.adx(df_1h['high'], df_1h['low'], df_1h['close'], length=14)
    dmi_4h = ta.adx(df_4h['high'], df_4h['low'], df_4h['close'], length=14)

    df_15m = pd.concat([df_15m, dmi_15m], axis=1)
    df_1h = pd.concat([df_1h, dmi_1h], axis=1)
    df_4h = pd.concat([df_4h, dmi_4h], axis=1)

    last_15m = df_15m.iloc[-1]
    prev_15m = df_15m.iloc[-2]
    last_1h = df_1h.iloc[-1]
    last_4h = df_4h.iloc[-1]

    # --- CONDITIONS ---

    # 4h condition: ADX > 20 and +DI > -DI
    if last_4h['ADX_14'] <= 20 or last_4h['DMP_14'] <= last_4h['DMN_14']:
        return None, f"❌ {symbol} - 4h trend weak (ADX={last_4h['ADX_14']:.2f}, +DI={last_4h['DMP_14']:.2f}, -DI={last_4h['DMN_14']:.2f})"
    
    # 1h condition: ADX > 20 and +DI > -DI
    if last_1h['ADX_14'] <= 20 or last_1h['DMP_14'] <= last_1h['DMN_14']:
        return None, f"❌ {symbol} - 1h trend weak (ADX={last_1h['ADX_14']:.2f}, +DI={last_1h['DMP_14']:.2f}, -DI={last_1h['DMN_14']:.2f})"

    # 15m condition: +DI > -DI
    #if not (prev_15m['DMP_14'] < prev_15m['DMN_14'] and last_15m['DMP_14'] > last_15m['DMN_14']):
    if not (last_15m['DMP_14'] > last_15m['DMN_14']):
        return None, f"❌ {symbol} - No bullish DI on 15m"

    # Volume filter
    volume_24h = get_24h_stats(symbol)
    if volume_24h is None or volume_24h < 20_000_000:
        return None, f"❌ {symbol} - Volume < $20M ({volume_24h})"

    # ✅ All conditions passed
    return {
        "symbol": symbol,
        "price": round(last_15m['close'], 4),
        "volume": round(volume_24h),
        "sg_time": get_singapore_time(),
        "ist_time": get_indian_time()
    }, None

# --- MAIN EXECUTION ---
def run_strategy():
    print("🔍 Starting Futures Signal Screener...\n")
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
            result, reason = check_conditions(symbol)
            if result:
                msg = (
                    f"✅ Futures Signal\n"
                    f"Symbol: {result['symbol']}\n"
                    f"Price: {result['price']}\n"
                    f"Volume: {result['volume']}\n"
                    f"Time (SGT): {result['sg_time']}\n"
                    f"Time (IST): {result['ist_time']}"
                )
                send_telegram_message(msg)
                valid_signals.append(result['symbol'])
                signals_sent += 1
                print(msg)
            else:
                print(reason)
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
        time.sleep(0.1)

    # Save results
    with open("future_usdt_signal.txt", "w") as f:
        for sym in valid_signals:
            f.write(sym + "\n")

    duration = time.time() - start_time
    print(f"\n✅ Done.\n🔢 Total Symbols: {total}\n📤 Signals Sent: {signals_sent}\n⏱️ Time: {duration:.2f} sec")

    summary = (
        f"✅ Futures Scan Complete\n"
        f"Total Symbols: {total}\n"
        f"Signals Sent: {signals_sent}\n"
        f"Time: {duration:.2f} sec\n"
        f"Time (IST): {get_indian_time()}"
    )
    send_telegram_message(summary)

# --- START ---
if __name__ == "__main__":
    run_strategy()
