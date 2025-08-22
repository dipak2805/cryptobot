import requests
import pandas as pd
import pandas_ta as ta
import time

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram send error: {e}")

def send_bb_signal_to_telegram(result):
    msg = (
        f"🔼 BB Signal\n"
        f"Symbol: {result['symbol']}\n"
        f"Price: {result['price']}\n"
        f"RSI: {result['rsi']}\n"
        f"BBL: {result['bbl']}\n"
        f"BBM: {result['bbm']}\n"
        f"BBU: {result['bbu']}\n"
        f"24h Change: {result['change_percent']}%\n"
        f"Volume Qty: {result['volume_qty']}"
    )

    print(f"[DEBUG] Sending to Telegram:\n{msg}\n")
    send_telegram_message(msg)

# --- GET KLINE DATA ---
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
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

# --- 24H STATS ---
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

# --- TREND STRENGTH CHECK (4H) ---
def is_uptrend(symbol):
    df = get_klines(symbol, interval="4h", limit=30)
    if df.empty:
        return False
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
    if df[['rsi', 'adx']].isna().any().any():
        return False
    current = df.iloc[-1]
    previous = df.iloc[-2]
    return (previous['adx'] > current['adx']) and (previous['rsi'] > current['rsi'])

# --- BB STRATEGY LOGIC (15M) ---
def bb_signal(symbol):
    df = get_klines(symbol, interval="15m", limit=30)
    if df.empty:
        return None

    bb = ta.bbands(df['close'], length=20, std=2.0)
    df = pd.concat([df, bb], axis=1)
    df['rsi'] = ta.rsi(df['close'], length=14)

    if df[['BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0', 'rsi']].isna().any().any():
        return None

    current = df.iloc[-1]
    previous = df.iloc[-2]
    prev2 = df.iloc[-3]

    change_percent, volume_qty, last_price = get_24h_stats(symbol)
    if volume_qty is None or volume_qty < 10_000_000:
        return None

    upper = current['BBU_20_2.0']
    middle = current['BBM_20_2.0']
    lower = current['BBL_20_2.0']
    price = current['close']
    mid_upper_half = middle + (upper - middle) / 2

    cond1 = (
        current['close'] > current['open'] and
        current['close'] > lower and
        current['close'] < middle and
        previous['low'] <= lower
    )

    cond2 = (
        price > middle and
        price < mid_upper_half and
        (previous['low'] < middle or prev2['low'] < middle)
    )

    if not (cond1 or cond2):
        return None

    return {
        "symbol": symbol,
        "price": round(price, 4),
        "rsi": round(current['rsi'], 2),
        "bbl": round(lower, 4),
        "bbm": round(middle, 4),
        "bbu": round(upper, 4),
        "change_percent": round(change_percent, 2),
        "volume_qty": round(volume_qty)
    }

# --- RUN SCREENING ---
def run_screener():
    print("🚀 Running BB Screener...")
    try:
        info = requests.get("https://api.binance.com/api/v3/exchangeInfo").json()
        usdt_pairs = [s['symbol'] for s in info['symbols']
                      if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING']
    except Exception as e:
        print(f"❌ Could not fetch USDT pairs: {e}")
        return

    matched_signals = []
    for symbol in usdt_pairs:
        try:
            print(f"🔍 Checking {symbol}")
            if not is_uptrend(symbol):
                continue
            result = bb_signal(symbol)
            if result:
                matched_signals.append(result)
                send_bb_signal_to_telegram(result)
                print("✅ Signal sent:", symbol)
                if len(matched_signals) >= 10:
                    print("🚫 Reached 10 signals limit.")
                    break
            time.sleep(0.1)
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")

    if not matched_signals:
        send_telegram_message("⚠️ No BB signals matched current market.")
    else:
        print(f"✅ {len(matched_signals)} signal(s) sent.")

# --- MAIN ---
if __name__ == "__main__":
    run_screener()
