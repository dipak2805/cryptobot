import requests
import pandas as pd
import pandas_ta as ta
import time

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = '8490094419:AAEQZNSe4JzxDRowNyscVHyjjz4clOfnp2k'
TELEGRAM_CHAT_ID = '555707299'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram send error: {e}")

# --- READ SYMBOLS FROM TXT ---
def load_symbol_list(filename="usdt_pairs.txt"):
    try:
        with open(filename, "r") as file:
            symbols = [line.strip().upper() for line in file if line.strip()]
        return symbols
    except Exception as e:
        print(f"❌ Error reading symbol list: {e}")
        return []

# --- GET CANDLE DATA ---
def get_klines(symbol, interval="1h", limit=5):
    url = f"https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
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

# --- GET 24H VOLUME ---
def get_24h_quote_volume(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        res = requests.get(url).json()
        return float(res["quoteVolume"])
    except Exception as e:
        print(f"Error fetching 24h volume for {symbol}: {e}")
        return 0

# --- CHECK STRATEGY CONDITIONS ---
def check_conditions(symbol):
    df = get_klines(symbol, interval="1h", limit=5)
    if len(df) < 4:
        print(f"{symbol} ❌ Not enough candles")
        return None

    # Candles
    prev2 = df.iloc[-3]
    prev1 = df.iloc[-2]
    curr = df.iloc[-1]

    # Current candle must be green
    if curr['close'] <= curr['open']:
        print(f"{symbol} ⛔ Current candle not green")
        return None

    # Previous candle low must be lower than both current and prev2
    if not (prev1['low'] < curr['low'] and prev1['low'] < prev2['low']):
        print(f"{symbol} ⛔ Prev1 low not lower than curr and prev2")
        return None

    # Price > open (if prev1 green) or > close (if prev1 red)
    if prev1['close'] > prev1['open']:
        if curr['close'] <= prev1['open']:
            print(f"{symbol} ⛔ Prev1 green, but curr price not above prev1 open")
            return None
    elif prev1['close'] < prev1['open']:
        if curr['close'] <= prev1['close']:
            print(f"{symbol} ⛔ Prev1 red, but curr price not above prev1 close")
            return None

    # RSI condition (placed last to avoid NaN failure)
    df['rsi'] = ta.rsi(df['close'], length=14)
    current_rsi = df['rsi'].iloc[-1]
    if pd.isna(current_rsi):
        print(f"{symbol} ⛔ RSI could not be calculated")
        return None
    if not (30 < current_rsi < 40):
        print(f"{symbol} ⛔ RSI {current_rsi:.2f} not in 30-60 range")
        return None

    # 24h volume
    quote_volume = get_24h_quote_volume(symbol)
    if quote_volume < 20_000_000:
        print(f"{symbol} ⛔ 24h quote volume < 20M (got {quote_volume:,.0f})")
        return None

    return {
        "symbol": symbol,
        "rsi": round(current_rsi, 2),
        "price": round(curr['close'], 4),
        "volume": round(quote_volume, 2)
    }

# --- MAIN EXECUTION ---
def run_strategy():
    print("🔍 Running 1H RSI + Candle Signal Screener...")
    start_time = time.time()

    target_symbols = load_symbol_list("usdt_pairs.txt")
    if not target_symbols:
        print("❌ No symbols loaded from txt.")
        return

    total_checked = 0
    total_signals = 0
    signals = []

    for symbol in target_symbols:
        if not symbol.endswith("USDT"):
            continue

        total_checked += 1
        print(f"\n🔁 Checking {symbol}")
        try:
            result = check_conditions(symbol)
            if result:
                message = (
                    f"📈 1H Signal Alert\n"
                    f"Symbol: {result['symbol']}\n"
                    f"RSI: {result['rsi']}\n"
                    f"Price: {result['price']}\n"
                    f"24h Volume: ${result['volume']:,.0f}"
                )
                send_telegram_message(message)
                print(f"✅ Signal Sent for {symbol}")
                signals.append(result)
                total_signals += 1
        except Exception as e:
            print(f"❌ Error with {symbol}: {e}")
        time.sleep(0.1)

    duration = time.time() - start_time
    summary = (
        f"✅ 1H Scan Complete\n"
        f"Total Symbols: {total_checked}\n"
        f"Signals Sent: {total_signals}\n"
        f"Time Taken: {duration:.2f} seconds"
    )
    print(summary)
    send_telegram_message(summary)

# --- START ---
if __name__ == "__main__":
    run_strategy()
