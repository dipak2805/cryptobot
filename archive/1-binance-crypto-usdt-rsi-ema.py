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
def get_klines(symbol, interval="15m", limit=100):
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
        df['close'] = pd.to_numeric(df['close'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

# --- GET 24H CHANGE + VOLUME ---
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

# --- SCREEN BASED ON RSI + EMA 21 CROSS ---
def rsi_signal(symbol):
    df = get_klines(symbol, interval="15m", limit=100)
    if df.empty:
        return None

    # Ensure numeric types
    for col in ['close', 'low', 'high']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Calculate indicators
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['atr14'] = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=14)

    df = df.dropna(subset=['rsi', 'ema21', 'atr14'])
    if len(df) < 2:
        print(f"⚠️ {symbol} - Not enough data after indicators")
        return None


    def get_singapore_time():
        tz = pytz.timezone("Asia/Singapore")
        sg_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        return sg_time


    # Get indicator values
    current_rsi = df['rsi'].iloc[-1]
    previous_rsi = df['rsi'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    curr_close = df['close'].iloc[-1]
    ema_now = df['ema21'].iloc[-1]
    curr_atr = df['atr14'].iloc[-1]
    prev_atr = df['atr14'].iloc[-2]

    # --- Conditions ---
    if not (40 < current_rsi < 60 and previous_rsi < current_rsi):
        return None
    if not (prev_low < ema_now and curr_close > ema_now):
        return None
    # if not (curr_atr >= prev_atr):
    #     print(f"⛔ {symbol} - ATR not rising")
    #     return None

    change_percent, usdt_volume_24h, last_price = get_24h_stats(symbol)
    if usdt_volume_24h is None or usdt_volume_24h <= 20_000_000:
        return None
    if change_percent is None or change_percent < -5:
        return None

    print(f"✅ {symbol} | RSI: {current_rsi:.2f} | EMA21: {ema_now:.2f} | ATR↑ {curr_atr:.2f} > {prev_atr:.2f}")

    return {
        "symbol": symbol,
        "rsi": round(current_rsi, 2),
        "p_rsi": round(previous_rsi, 2),
        "ema21": round(ema_now, 2),
        "atr_now": round(curr_atr, 4),
        "atr_prev": round(prev_atr, 4),
        "change_percent": round(change_percent, 2),
        "usdt_volume_24h": round(usdt_volume_24h),
        "price": round(last_price, 4),
        "sg_time": get_singapore_time() 
    }

# --- MAIN EXECUTION ---
def run_rsi_screener():
    print("🔍 Running RSI Screener...")

    target_symbols = load_symbol_list("usdt_pairs.txt")
    if not target_symbols:
        print("❌ No symbols loaded from txt.")
        return

    signals = []
    max_signals = 5
    signal_count = 0

    for symbol in target_symbols:
        print(f"🔁 Checking {symbol}")
        try:
            result = rsi_signal(symbol)
            if result:
                signals.append(result)
                msg = (
                    f"🚀 R54050E21 Signal\n"
                    f"Symbol: {result['symbol']}\n"
                    f"RSI: {result['rsi']} (Prev: {result['p_rsi']})\n"
                    f"EMA21: {result['ema21']}\n"
                    f"24h Change: {result['change_percent']}%\n"
                    f"USDT Volume: {result['usdt_volume_24h']}\n"
                    f"Price: {result['price']}\n"
                    f"Date/Time (SGT): {result['sg_time']}"
                )
                print(msg)
                send_telegram_message(msg)
                signal_count += 1
                if signal_count >= max_signals:
                    print("🚫 Reached max signal limit. Exiting early.")
                    break
        except Exception as e:
            print(f"❌ Error in {symbol}: {e}")
        time.sleep(0.1)

    if not signals:
        print("\n⚠️ No signals found.")
        send_telegram_message("⚠️ No RSI + EMA21 signals found.")
    else:
        print(f"\n✅ Done. {len(signals)} signals found.\n")

# --- START ---
if __name__ == "__main__":
    run_rsi_screener()
