import requests
import pandas as pd
import pandas_ta as ta
import time

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

def send_signal_to_telegram(result):
    msg = (
        f"🔥Uptrend Signal\n"
        f"Symbol: {result['symbol']}\n"
        f"Price: {result['price']}\n"
        f"RSI (15m): {result['rsi']}\n"
        f"24h Change: {result['change_percent']}%\n"
        f"Volume USDT: {result['volume_qty']}"
    )
    print(f"[ALERT] {result['symbol']} ✅ Signal matched.\n")
    send_telegram_message(msg)

def get_klines(symbol, interval="15m", limit=100):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'num_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

def get_24h_stats(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        res = requests.get(url).json()
        return (
            round(float(res["priceChangePercent"]), 2),
            round(float(res["quoteVolume"])),
            float(res["lastPrice"])
        )
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return 0.0, 0, 0.0

def is_4h_uptrend(symbol):
    df = get_klines(symbol, interval="4h", limit=30)
    if df.empty:
        print(f"⚠️ {symbol} - No 4H data.")
        return False

    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
    df['ema_12'] = ta.ema(df['close'], length=12)

    current = df.iloc[-1]
    previous = df.iloc[-2]

    if pd.isna(current['rsi']) or pd.isna(current['adx']) or pd.isna(current['ema_12']):
        print(f"⚠️ {symbol} - NaN in ADX/RSI/EMA.")
        return False

    return current['adx'] > 25 and current['rsi'] > 30 and (current['adx'] >= previous['adx']) and current['close'] > current['ema_12']    

def check_conditions(symbol):
    print(f"🔍 Checking {symbol}...")

    change_percent, usdt_volume_24h, price = get_24h_stats(symbol)
    
    df_15m = get_klines(symbol, interval="15m", limit=30)
    if df_15m.empty:
        print(f"⚠️ Skipping {symbol} - No 15m data.")
        return None

    df_15m['rsi'] = ta.rsi(df_15m['close'], length=14)
    current = df_15m.iloc[-1]
    rsi_15m = current['rsi']
    volume_15m = current['volume']

    if not is_4h_uptrend(symbol):
        print(f"⛔ {symbol} - Not in confirmed 4H uptrend.")
        return None

    if not (rsi_15m >= 30):
        print(f"⛔ {symbol} - RSI 15m {rsi_15m:.2f} not greater than 30.")
        return None

    if usdt_volume_24h < 100_000_000:
        print(f"⛔ {symbol} - 24h USDT Volume {usdt_volume_24h:.0f} < 100M.")
        return None

    return {
        'symbol': symbol,
        'price': round(price, 4),
        'rsi': round(rsi_15m, 2),
        'change_percent': change_percent,
        'volume_qty': round(usdt_volume_24h)
    }

def main():
    print("🚀 Starting signal scan...")
    start_time = time.time()

    try:
        with open("usdt_pairs.txt", "r") as f:
            usdt_pairs = [line.strip().upper() for line in f if line.strip()]
        print(f"📊 Loaded {len(usdt_pairs)} USDT pairs from file.")
    except Exception as e:
        print(f"Failed to read input file: {e}")
        return

    processed_count = 0
    signal_count = 0

    for symbol in usdt_pairs:
        result = check_conditions(symbol)
        processed_count += 1
        if result:
            signal_count += 1
            send_signal_to_telegram(result)
        time.sleep(0.1)

    total_time = round(time.time() - start_time, 2)

    print(f"\n✅ Finished scanning.")
    print(f"🔢 Total pairs processed: {processed_count}")
    print(f"📩 Signals sent: {signal_count}")
    print(f"⏱️ Execution time: {total_time} seconds")

if __name__ == "__main__":
    main()
