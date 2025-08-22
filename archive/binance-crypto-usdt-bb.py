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

# --- LOAD SYMBOLS FROM TXT FILE ---
def load_symbol_list(filename="usdt_pairs.txt"):
    try:
        with open(filename, "r") as f:
            return [line.strip().upper() for line in f if line.strip()]
    except Exception as e:
        print(f"❌ Failed to read {filename}: {e}")
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
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
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
            float(res["volume"]),
            float(res["lastPrice"])
        )
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return None, None, None

# --- BOLLINGER BAND SIGNAL LOGIC ---
def bb_signal(symbol):
    df = get_klines(symbol, interval="15m", limit=30)
    if df.empty:
        return None

    df['close'] = pd.to_numeric(df['close'])
    df['low'] = pd.to_numeric(df['low'])
    df['high'] = pd.to_numeric(df['high'])
    df['open'] = pd.to_numeric(df['open'])

    bb = ta.bbands(df['close'], length=20, std=2.0)
    df = pd.concat([df, bb], axis=1)

    if df[['BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0']].isna().any().any():
        return None

    current = df.iloc[-1]
    previous = df.iloc[-2]
    prev2 = df.iloc[-3]

    # 24h stats
    change_percent, volume_qty, last_price = get_24h_stats(symbol)

    # --- CONDITION 1: BB Lower Band Bounce ---
    cond1 = (
        current['close'] > current['open'] and  # green candle
        current['close'] > current['BBL_20_2.0'] and
        current['close'] < current['BBM_20_2.0'] and
        previous['low'] <= previous['BBL_20_2.0']
    )

    # --- CONDITION 2: BB Middle Reclaim with RSI ---
    df['rsi'] = ta.rsi(df['close'], length=14)
    if pd.isna(current['rsi']):
        return None
    rsi_ok = 40 <= current['rsi'] <= 55

    upper = current['BBU_20_2.0']
    middle = current['BBM_20_2.0']
    lower = current['BBL_20_2.0']
    price = current['close']
    mid_upper_half = middle + (upper - middle) / 2

    cond2 = (
        price > middle and
        (previous['low'] < middle or prev2['low'] < middle) and
        price < mid_upper_half and
        rsi_ok
    )

    # --- SIGNAL EVALUATION ---
    if cond1:
        label = "🔽 BB Lower Band Bounce"
    elif cond2:
        label = "🔼 BB Middle Reclaim"
    else:
        return None

    print(
        f"✅ {symbol} - {label} | Price: {round(price, 4)} | Vol Qty: {round(volume_qty)} | RSI: {round(current['rsi'], 2)} | "
        f"BBL: {round(lower, 4)} | BBM: {round(middle, 4)} | BBU: {round(upper, 4)}"
    )

    return {
        "symbol": symbol,
        "label": label,
        "price": round(price, 4),
        "change_percent": round(change_percent, 2),
        "volume_qty": round(volume_qty),
        "rsi": round(current['rsi'], 2),
        "bbu": round(upper, 4),
        "bbm": round(middle, 4),
        "bbl": round(lower, 4)
    }

# --- MAIN ---
def run_bb_screener():
    print("🔍 Running Simplified BBands Screener...")

    usdt_pairs = load_symbol_list("usdt_pairs.txt")
    if not usdt_pairs:
        print("❌ No USDT pairs loaded from file.")
        return

    signals = []
    max_signals = 5
    signal_count = 0

    for symbol in usdt_pairs:
        print(f"🔁 Checking {symbol}")
        try:
            result = bb_signal(symbol)
            if result:
                signals.append(result)
                msg = (
                    f"{result['label']}\n"
                    f"Symbol: {result['symbol']}\n"
                    f"Price: {result['price']}\n"
                    f"RSI: {result['rsi']}\n"
                    f"BBL: {result['bbl']}\n"
                    f"BBM: {result['bbm']}\n"
                    f"BBU: {result['bbu']}\n"
                    f"24h Change: {result['change_percent']}%\n"
                    f"Volume Qty: {result['volume_qty']}"
                )
                send_telegram_message(msg)
                signal_count += 1
                print(f"signal_count: {signal_count}")
                if signal_count >= max_signals:
                    print("🚫 Reached max signal limit. Exiting early.")
                    break
        except Exception as e:
            print(f"❌ Error in {symbol}: {e}")
        time.sleep(0.1)  # Respect API limits

    if not signals:
        print("\n⚠️ No Bollinger Band signals found.")
        send_telegram_message("⚠️ No BBands signals found.")
    else:
        print(f"\n✅ Done. {len(signals)} signals found.\n")

# --- START ---
if __name__ == "__main__":
    run_bb_screener()
