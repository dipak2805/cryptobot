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
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram send error: {e}")

# --- READ SYMBOLS FROM FILE ---
def load_usdt_symbols(filename="usdt_pairs.txt"):
    try:
        with open(filename, "r") as f:
            return [line.strip().upper() for line in f if line.strip()]
    except Exception as e:
        print(f"Error loading symbols: {e}")
        return []

# --- GET CANDLE DATA ---
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
        df['close'] = pd.to_numeric(df['close'])
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

# --- GET 24H STATS ---
def get_24h_stats(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        res = requests.get(url).json()
        return (
            float(res["priceChangePercent"]),
            float(res["quoteVolume"]),
            float(res["lastPrice"])
        )
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return None, None, None

def get_singapore_time():
    tz = pytz.timezone("Asia/Singapore")
    sg_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    return sg_time


# --- RSI LOGIC ---
def rsi_signal(symbol):
    df = get_klines(symbol, interval="15m", limit=100)
    if df.empty:
        return None

    df['rsi'] = ta.rsi(df['close'], length=14)
    current_rsi = df['rsi'].iloc[-1]
    previous_rsi = df['rsi'].iloc[-2]

    if pd.isna(current_rsi) or pd.isna(previous_rsi):
        print(f"⚠️ {symbol} - RSI is NaN")
        return None

    if 40 < current_rsi < 50 and previous_rsi < current_rsi:
        change_percent, volume_qty, last_price = get_24h_stats(symbol)
        if volume_qty is None or volume_qty <= 30_000_000:
            print(f"⛔ {symbol} - USDT Volume {volume_qty} below 30M")
            return None
        if change_percent is None or change_percent <= -5:
            print(f"⛔ {symbol} - 24H Change % {change_percent} below -5%")
            return None

        print(f"✅ {symbol} passed - RSI: {round(current_rsi, 2)} | Price: {last_price} | Change: {round(change_percent, 2)}% | Volume: {round(volume_qty)}")
        return {
            "symbol": symbol,
            "rsi": round(current_rsi, 2),
            "p_rsi": round(previous_rsi, 2),
            "change_percent": round(change_percent, 2),
            "usdt_volume_qty": round(volume_qty, 2),
            "price": round(last_price, 4),
            "sg_time": get_singapore_time() 
        }
    return None


# --- MAIN ---
def run_rsi_screener():
    print("🔍 Running RSI Screener...\n")
    start_time = time.time()

    symbols = load_usdt_symbols("usdt_pairs.txt")
    if not symbols:
        print("❌ No USDT symbols loaded.")
        return

    total = 0
    signals_sent = 0
    max_signals = 5
    signals = []

    for symbol in symbols:
        total += 1
        print(f"\n🔁 Checking {symbol}")
        try:
            result = rsi_signal(symbol)
            if result:
                signals.append(result)
                msg = (
                    f"🟢 3050 Signal\n"
                    f"Symbol: {result['symbol']}\n"
                    f"RSI: {result['rsi']}\n"
                    f"Prev RSI: {result['p_rsi']}\n"
                    f"24h Change: {result['change_percent']}%\n"
                    f"24h Volume: {result['usdt_volume_qty']}\n"
                    f"Price: {result['price']}\n"
                    f"Date/Time (SGT): {result['sg_time']}"
                )
                send_telegram_message(msg)
                signals_sent += 1
                if signals_sent >= max_signals:
                    print("🚫 Reached max signal limit. Exiting early.")
                    break
        except Exception as e:
            print(f"❌ Error in {symbol}: {e}")
        time.sleep(0.1)  # Binance rate limit

    duration = time.time() - start_time

    # --- SUMMARY ---
    print(f"\n✅ Done.\n🔢 Total Symbols: {total}\n📤 Signals Sent: {signals_sent}\n⏱️ Time Taken: {duration:.2f} sec")
    send_telegram_message(
        f"✅ RSI Screener Complete\n"
        f"Total Symbols: {total}\n"
        f"Signals Sent: {signals_sent}\n"
        f"Time Taken: {duration:.2f} sec"
    )

# --- START ---
if __name__ == "__main__":
    run_rsi_screener()
