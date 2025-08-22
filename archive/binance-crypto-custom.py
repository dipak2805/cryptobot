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
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

# --- GET 24H CHANGE ---
def get_24h_stats(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        res = requests.get(url).json()
        return float(res["priceChangePercent"])
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return None

# --- SCREEN BASED ON RSI ONLY ---
def rsi_signal(symbol):
    df = get_klines(symbol, interval="15m", limit=20)
    if df.empty:
        return None

    df['rsi'] = ta.rsi(df['close'], length=14)
    current_rsi = df['rsi'].iloc[-1]

    if pd.isna(current_rsi):
        print(f"⚠️ {symbol} - RSI is NaN")
        return None

    if 30 < current_rsi < 50:
        print(f"✅ {symbol} - RSI in range: {round(current_rsi, 2)}")
        change_percent = get_24h_stats(symbol)
        return {
            "symbol": symbol,
            "rsi": round(current_rsi, 2),
            "change_percent": round(change_percent, 2) if change_percent is not None else "N/A"
        }

    return None

# --- MAIN EXECUTION ---
def run_rsi_screener():
    print("🔍 Running RSI Screener...")
    try:
        info = requests.get("https://api.binance.com/api/v3/exchangeInfo").json()
        usdt_pairs = [s['symbol'] for s in info['symbols']
                      if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING']
    except Exception as e:
        print(f"❌ Failed to get trading pairs: {e}")
        return

    if not usdt_pairs:
        print("❌ No USDT pairs found.")
        return

    signals = []

    for symbol in usdt_pairs:
        print(f"🔁 Checking {symbol}")
        try:
            result = rsi_signal(symbol)
            if result:
                signals.append(result)
                msg = (
                    f"📈 {result['symbol']} Signal\n"
                    f"RSI: {result['rsi']}\n"
                    f"24h Change: {result['change_percent']}%"
                )
                print(msg)
                send_telegram_message(msg)
        except Exception as e:
            print(f"❌ Error in {symbol}: {e}")
        time.sleep(0.1)  # Binance rate limits

    if not signals:
        print("\n⚠️ No matches found (RSI 30–50)")
        send_telegram_message("⚠️ No RSI signals found (RSI between 30 and 50)")
    else:
        print(f"\n✅ Done. {len(signals)} signals found.\n")

# --- START ---
if __name__ == "__main__":
    run_rsi_screener()
