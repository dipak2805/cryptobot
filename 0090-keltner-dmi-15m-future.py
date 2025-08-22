import requests
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
import pytz

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = '8490094419:AAHiq6NKVyogWirW8byVT3125XMO-d2ZA1s'
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

# --- GET 15M CANDLE DATA FROM FUTURES ---
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
    df = get_klines(symbol, interval="15m", limit=100)
    if len(df) < 21:
        print(f"⛔ {symbol} - Not enough candles")
        return None

    # --- Keltner Channel ---
    kc = ta.kc(df['high'], df['low'], df['close'], length=20, scalar=2, mamode="ema", atr_length=10)
    df = pd.concat([df, kc], axis=1)

    # --- DMI ---
    dmi = ta.adx(df['high'], df['low'], df['close'], length=14)
    df = pd.concat([df, dmi], axis=1)

    curr = df.iloc[-1]

    # Condition 1: Close >= KC basis
    if curr['close'] < curr['KCLe_20_2.0']:
        print(f"❌ {symbol} - Close below Keltner basis")
        return None

    # Condition 2: +DI >= 25 and > -DI
    if curr['DMP_14'] < 25 or curr['DMP_14'] <= curr['DMN_14']:
        print(f"❌ {symbol} - DMI condition failed (+DI={curr['DMP_14']:.2f}, -DI={curr['DMN_14']:.2f})")
        return None

    # Volume filter
    volume_24h = get_24h_stats(symbol)
    if volume_24h is None or volume_24h < 20_000_000:
        print(f"❌ {symbol} - Volume < $20M ({volume_24h})")
        return None

    print(f"✅ {symbol} passed all checks")
    return {
        "symbol": symbol,
        "price": round(curr['close'], 4),
        "volume": round(volume_24h),
        "sg_time": get_singapore_time()
    }

# --- MAIN EXECUTION ---
def run_strategy():
    print("🔍 Starting 15m Futures Signal Screener...\n")
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
                msg = (
                    f"✅ 15m Futures Signal\n"
                    f"Symbol: {result['symbol']}\n"
                    f"Price: {result['price']}\n"
                    f"Volume: {result['volume']}\n"
                    f"Time (SGT): {result['sg_time']}"
                )
                send_telegram_message(msg)
                valid_signals.append(result['symbol'])
                signals_sent += 1
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
        time.sleep(0.1)

    # Write results to file
    with open("future_usdt_15m_signal.txt", "w") as f:
        for sym in valid_signals:
            f.write(sym + "\n")

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
