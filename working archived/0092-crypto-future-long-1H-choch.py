import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz
import os

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = "your_telegram_token"
TELEGRAM_CHAT_ID = "your_chat_id"

# --- FILE PATHS ---
PAIRS_FILE = "future_usdt_usdm_pairs.txt"
TRIGGER_FILE = "triggered_symbols.txt"

# --- SETTINGS ---
TIMEFRAME = "1h"
SWING_LENGTH = 2  # Adjustable swing length for CHoCH
RESET_HOURS = 4   # Reset triggered list every 4 hours

# --- TIMEZONE ---
SG_TZ = pytz.timezone("Asia/Singapore")

# --- SEND TELEGRAM MESSAGE ---
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram send failed: {e}")

# --- LOAD TRIGGERED SYMBOLS ---
def load_triggered_symbols():
    if not os.path.exists(TRIGGER_FILE):
        return []
    with open(TRIGGER_FILE, "r") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

# --- SAVE TRIGGERED SYMBOL ---
def save_triggered_symbol(symbol):
    with open(TRIGGER_FILE, "a") as f:
        f.write(symbol + "\n")

# --- RESET TRIGGER FILE ---
def reset_trigger_file_if_needed():
    reset_file = "last_reset.txt"
    now_sg = datetime.now(SG_TZ)

    if not os.path.exists(reset_file):
        with open(reset_file, "w") as f:
            f.write(now_sg.strftime("%Y-%m-%d %H:%M:%S"))
        return

    with open(reset_file, "r") as f:
        last_reset_str = f.read().strip()
    last_reset = SG_TZ.localize(datetime.strptime(last_reset_str, "%Y-%m-%d %H:%M:%S"))

    if now_sg - last_reset >= timedelta(hours=RESET_HOURS):
        open(TRIGGER_FILE, "w").close()  # clear file
        with open(reset_file, "w") as f:
            f.write(now_sg.strftime("%Y-%m-%d %H:%M:%S"))
        print(f"🔄 Triggered symbols reset at {now_sg.strftime('%Y-%m-%d %H:%M:%S')} SG time")

# --- FETCH DATA ---
def get_klines(symbol, interval, limit=200):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","num_trades","taker_base_vol","taker_quote_vol","ignore"
        ])
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

# --- FIND SWING HIGH / LOW ---
def is_swing_high(df, idx, length):
    return all(df["high"].iloc[idx] > df["high"].iloc[idx - i] and df["high"].iloc[idx] > df["high"].iloc[idx + i] for i in range(1, length + 1))

def is_swing_low(df, idx, length):
    return all(df["low"].iloc[idx] < df["low"].iloc[idx - i] and df["low"].iloc[idx] < df["low"].iloc[idx + i] for i in range(1, length + 1))

# --- DETECT BULLISH CHoCH ---
def detect_bullish_choch(df, swing_length):
    df["SMA7"] = ta.sma(df["close"], 7)
    df["SMA25"] = ta.sma(df["close"], 25)

    if df["SMA7"].iloc[-1] <= df["SMA25"].iloc[-1]:
        return False

    last_swing_low_idx = None
    last_swing_high_idx = None

    for i in range(swing_length, len(df) - swing_length):
        if is_swing_low(df, i, swing_length):
            last_swing_low_idx = i
        if is_swing_high(df, i, swing_length):
            last_swing_high_idx = i

    if last_swing_low_idx and last_swing_high_idx:
        if last_swing_low_idx > last_swing_high_idx:
            if df["close"].iloc[-1] > df["high"].iloc[last_swing_high_idx]:
                return True
    return False

# --- MAIN SCRIPT ---
def main():
    reset_trigger_file_if_needed()
    triggered_symbols = load_triggered_symbols()

    total_signals = 0

    if not os.path.exists(PAIRS_FILE):
        print(f"❌ Pairs file {PAIRS_FILE} not found.")
        return

    with open(PAIRS_FILE, "r") as f:
        symbols = [line.strip() for line in f.readlines() if line.strip()]

    for symbol in symbols:
        print(f"🔍 Checking: {symbol}")

        if symbol in triggered_symbols:
            continue

        df = get_klines(symbol, TIMEFRAME)
        if df is None or len(df) < 50:
            continue

        if detect_bullish_choch(df, SWING_LENGTH):
            cmp_price = df["close"].iloc[-1]
            msg = f"✅ Long Signal: {symbol} | CMP: {cmp_price}"
            send_telegram_message(msg)
            print(msg)

            save_triggered_symbol(symbol)
            total_signals += 1

    print(f"📊 Total Signals This Run: {total_signals}")

    # --- Show all triggered signals at the end ---
    print("\n📄 Current Triggered Signals List:")
    all_triggers = load_triggered_symbols()
    if all_triggers:
        for s in all_triggers:
            print(f" - {s}")
    else:
        print(" (No signals stored yet)")

if __name__ == "__main__":
    main()
