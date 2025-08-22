import requests
import pandas as pd
from datetime import datetime
import pytz

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = "your_telegram_token"
TELEGRAM_CHAT_ID = "your_chat_id"

# --- BINANCE API ---
BASE_URL = "https://fapi.binance.com/fapi/v1/klines"
PAIRS_FILE = "future_usdt_usdm_pairs.txt"

# --- TIMEZONE ---
SGT = pytz.timezone("Asia/Singapore")

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_ohlcv(symbol, interval="1h", limit=100):
    url = f"{BASE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","num_trades","taker_base","taker_quote","ignore"
    ])

    df[["open","high","low","close","volume"]] = df[["open","high","low","close","volume"]].astype(float)
    return df

def compute_mfi(df, length=14):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    rmf = tp * df["volume"]

    positive_flow, negative_flow = [0], [0]
    for i in range(1, len(tp)):
        if tp.iloc[i] > tp.iloc[i-1]:
            positive_flow.append(rmf.iloc[i])
            negative_flow.append(0)
        elif tp.iloc[i] < tp.iloc[i-1]:
            positive_flow.append(0)
            negative_flow.append(rmf.iloc[i])
        else:
            positive_flow.append(0)
            negative_flow.append(0)

    df["pos_mf"] = positive_flow
    df["neg_mf"] = negative_flow

    pos_mf_sum = df["pos_mf"].rolling(window=length).sum()
    neg_mf_sum = df["neg_mf"].rolling(window=length).sum()

    mfr = pos_mf_sum / neg_mf_sum.replace(0, 1)
    df["mfi"] = 100 - (100 / (1 + mfr))

    return df

def check_signal(df, symbol, ob=80, os=20):
    if len(df.dropna()) < 2:
        return None

    prev = df["mfi"].iloc[-2]
    curr = df["mfi"].iloc[-1]

    # Singapore timestamp
    now_sgt = datetime.now(SGT).strftime("%Y-%m-%d %H:%M:%S")

    # ✅ Corrected crossing logic
    if prev >= os and curr < os:
        return f"[{now_sgt}] {symbol} -> OVERSOLD ({curr:.2f})"
    elif prev <= ob and curr > ob:
        return f"[{now_sgt}] {symbol} -> OVERBOUGHT ({curr:.2f})"
    else:
        # If no signal, show the latest MFI value
        print(f"[{now_sgt}] {symbol} -> MFI = {curr:.2f}")
        return None

if __name__ == "__main__":
    with open(PAIRS_FILE, "r") as f:
        pairs = [line.strip() for line in f.readlines() if line.strip()]

    for idx, symbol in enumerate(pairs, 1):
        try:
            print(f"[{idx}/{len(pairs)}] Checking {symbol} ...", end="\r")
            df = get_ohlcv(symbol, "1h", 150)
            df = compute_mfi(df)
            signal = check_signal(df, symbol)
            if signal:
                print(f"\n{signal}")
                send_telegram_message(signal)
        except Exception as e:
            print(f"\n{symbol} -> Error: {e}")
            continue

    print("\n✅ Scan completed.")
