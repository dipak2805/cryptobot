import requests
import pandas as pd
import time
from datetime import datetime
import pytz
import math

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = ''
TELEGRAM_CHAT_ID = ''

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured — skipping send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload, timeout=10)
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

def get_klines(symbol, interval="15m", limit=300):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'num_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return pd.DataFrame()

def get_24h_stats(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
        res = requests.get(url, timeout=10).json()
        return float(res.get("quoteVolume", 0))
    except Exception as e:
        print(f"Error getting 24h stats for {symbol}: {e}")
        return None

# --- Custom TradingView-style SMI ---
def smi_tradingview(df, length=21, smooth_k=5, smooth_d=5):
    high = df['high']
    low = df['low']
    close = df['close']

    hl = (high.rolling(length).max() + low.rolling(length).min()) / 2
    diff = close - hl
    hl_range = (high.rolling(length).max() - low.rolling(length).min())

    diff_smoothed = diff.ewm(span=smooth_k).mean().ewm(span=smooth_k).mean()
    hl_smoothed = hl_range.ewm(span=smooth_k).mean().ewm(span=smooth_k).mean()

    smi = 100 * (diff_smoothed / (hl_smoothed / 2))
    smi_signal = smi.ewm(span=smooth_d).mean()

    return smi, smi_signal

def get_latest_smi(symbol, interval="15m"):
    df = get_klines(symbol, interval=interval, limit=300)
    if df.empty or len(df) < 50:
        return None, None, None
    smi_series, smi_signal_series = smi_tradingview(df, length=21, smooth_k=5, smooth_d=5)
    return (
        float(df['close'].iat[-1]),
        float(smi_series.iat[-1]),
        float(smi_signal_series.iat[-1])
    )

def check_conditions(symbol):
    # --- 15m timeframe ---
    close_15, smi_15, signal_15 = get_latest_smi(symbol, interval="15m")
    if smi_15 is None:
        return None

    # --- 30m timeframe ---
    close_30, smi_30, signal_30 = get_latest_smi(symbol, interval="30m")
    if smi_30 is None:
        return None

    # Debug print
    print(f"📊 {symbol} | 15m SMI={smi_15:.2f}/{signal_15:.2f}, 30m SMI={smi_30:.2f}/{signal_30:.2f}")

    # --- Strategy Condition for SHORT ---
    cond_15 = smi_15 < signal_15 and smi_15 > 0
    cond_30 = smi_30 < signal_30

    if not (cond_15 and cond_30):
        print(f"🔴 {symbol} - Condition failed")
        return None

    # --- Volume filter ---
    volume_24h = get_24h_stats(symbol)
    if volume_24h is None or volume_24h < 20_000_000:
        print(f"🔴 {symbol} - Volume < $20M ({volume_24h})")
        return None

    print(f"🟢 {symbol} passed all checks")
    return {
        "symbol": symbol,
        "price": round(close_15, 6),
        "volume": round(volume_24h),
        "sg_time": get_singapore_time(),
        "smi_15": smi_15,
        "signal_15": signal_15,
        "smi_30": smi_30,
        "signal_30": signal_30,
    }

def run_strategy():
    print("🔍 Starting Futures SHORT Screener (15m + 30m)...\n")
    start_time = time.time()

    target_symbols = load_symbol_list("future_usdt_usdm_pairs.txt")
    if not target_symbols:
        print("🔴 No symbols loaded from txt.")
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
                    f"⚠️ Futures SHORT Signal\n"
                    f"Symbol: {result['symbol']}\n"
                    f"Price: {result['price']}\n"
                    f"Volume: {result['volume']}\n"
                    f"15m SMI: {result['smi_15']:.2f} (Signal: {result['signal_15']:.2f})\n"
                    f"30m SMI: {result['smi_30']:.2f} (Signal: {result['signal_30']:.2f})\n"
                    f"Time (SGT): {result['sg_time']}"
                )
                send_telegram_message(msg)
                valid_signals.append(result['symbol'])
                signals_sent += 1
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
        time.sleep(0.1)

    with open("future_usdt_15m_short_signal.txt", "w") as f:
        for sym in valid_signals:
            f.write(sym + "\n")

    duration = time.time() - start_time
    print(f"\n✅ Done.\n🔢 Total Symbols: {total}\n📤 Signals Sent: {signals_sent}\n⏱️ Time: {duration:.2f} sec")

    summary = (
        f"⚠️ Futures SHORT Scan Complete (15m + 30m)\n"
        f"Total Symbols: {total}\n"
        f"Signals Sent: {signals_sent}\n"
        f"Time: {duration:.2f} sec"
    )
    send_telegram_message(summary)

if __name__ == "__main__":
    run_strategy()
