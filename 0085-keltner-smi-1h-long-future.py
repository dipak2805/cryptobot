import requests
import pandas as pd
import pandas_ta as ta
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

def get_klines(symbol, interval="1h", limit=200):
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

def check_conditions(symbol):
    # Use 1h candles as requested
    df = get_klines(symbol, interval="1h", limit=300)
    if df.empty or len(df) < 50:
        print(f"⛔ {symbol} - Not enough candles ({len(df)})")
        return None

    # --- Keltner basis (EMA 20) and ATR(10) ---
    try:
        kc_basis_series = ta.ema(df['close'], length=20)   # EMA(20) middle band
        atr_series = ta.atr(df['high'], df['low'], df['close'], length=10)
        # note: kc_upper/lower not needed for condition but computed for debug if wanted
        kc_upper_series = kc_basis_series + 2.0 * atr_series
        kc_lower_series = kc_basis_series - 2.0 * atr_series
    except Exception as e:
        print(f"⚠️ {symbol} - Error computing Keltner components: {e}")
        return None

    # --- SMI (map your 21,5,5 -> slow=21, fast=5, signal=5) ---
    # pandas_ta.smi signature: smi(close, fast=None, slow=None, signal=None)
    try:
        smi_df = ta.smi(df['close'], fast=5, slow=21, signal=5)
    except Exception as e:
        print(f"⚠️ {symbol} - Error computing SMI: {e}")
        return None

    # Debug: show what columns were returned
    if isinstance(smi_df, (pd.DataFrame, pd.Series)):
        print(f"📊 {symbol} - SMI output cols: {list(getattr(smi_df, 'columns', [smi_df.name]))}")
    else:
        print(f"📊 {symbol} - SMI returned unexpected type: {type(smi_df)}")

    # Extract SMI and its signal robustly
    try:
        if isinstance(smi_df, pd.DataFrame):
            # per pandas_ta, first col = smi, second = signal, third = osc (if present)
            if smi_df.shape[1] >= 2:
                smi_series = smi_df.iloc[:, 0]
                smi_signal_series = smi_df.iloc[:, 1]
            else:
                # fallback: single column -> treat as smi and compute signal as ema(smi, length=5)
                smi_series = smi_df.iloc[:, 0]
                smi_signal_series = ta.ema(smi_series, length=5)
        elif isinstance(smi_df, pd.Series):
            smi_series = smi_df
            smi_signal_series = ta.ema(smi_series, length=5)
        else:
            print(f"⚠️ {symbol} - unexpected SMI return type: {type(smi_df)}")
            return None
    except Exception as e:
        print(f"⚠️ {symbol} - Error extracting SMI series: {e}")
        return None

    # --- Extract last scalar values safely ---
    try:
        close_val = float(df['close'].iat[-1])
        kc_basis_val = float(kc_basis_series.iat[-1])
        smi_val = float(smi_series.iat[-1])
        smi_signal_val = float(smi_signal_series.iat[-1])
    except Exception as e:
        print(f"⚠️ {symbol} - Could not extract last values: {e}")
        return None

    # Check for NaNs
    if any(math.isnan(x) for x in [close_val, kc_basis_val, smi_val, smi_signal_val]):
        print(f"⚠️ {symbol} - NaN in indicators (close={close_val}, kc_basis={kc_basis_val}, smi={smi_val}, signal={smi_signal_val})")
        return None

    # Debug print
    print(f"📈 {symbol} - Close={close_val:.6f}, KC_basis={kc_basis_val:.6f}, SMI={smi_val:.4f}, SMI_signal={smi_signal_val:.4f}")

    # --- Strategy Conditions (as you requested) ---
    # 1) On 1h: price (close) is above middle band (KC basis)
    if close_val < kc_basis_val:
        print(f"❌ {symbol} - Close below Keltner basis")
        return None

    # 2) SMI > SMI signal (EMA)
    if smi_val <= smi_signal_val:
        print(f"❌ {symbol} - SMI condition failed (SMI={smi_val:.4f} <= Signal={smi_signal_val:.4f})")
        return None

    # 3) Volume 24h filter (quote volume)
    volume_24h = get_24h_stats(symbol)
    if volume_24h is None or volume_24h < 20_000_000:
        print(f"❌ {symbol} - Volume < $20M ({volume_24h})")
        return None

    print(f"✅ {symbol} passed all checks")
    return {
        "symbol": symbol,
        "price": round(close_val, 6),
        "volume": round(volume_24h),
        "sg_time": get_singapore_time(),
        "kc_basis": kc_basis_val,
        "smi": smi_val,
        "smi_signal": smi_signal_val
    }

def run_strategy():
    print("🔍 Starting 1h Futures Signal Screener...\n")
    start_time = time.time()

    target_symbols = load_symbol_list("future_usdt_usdm_pairs.txt")
    if not target_symbols:
        print("❌ No symbols loaded from txt.")
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
                    f"✅ 1h Futures Signal\n"
                    f"Symbol: {result['symbol']}\n"
                    f"Price: {result['price']}\n"
                    f"Volume: {result['volume']}\n"
                    f"KC_basis: {result['kc_basis']:.6f}\n"
                    f"SMI: {result['smi']:.4f} (Signal: {result['smi_signal']:.4f})\n"
                    f"Time (SGT): {result['sg_time']}"
                )
                send_telegram_message(msg)
                valid_signals.append(result['symbol'])
                signals_sent += 1
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
        time.sleep(0.1)

    with open("future_usdt_1h_signal.txt", "w") as f:
        for sym in valid_signals:
            f.write(sym + "\n")

    duration = time.time() - start_time
    print(f"\n✅ Done.\n🔢 Total Symbols: {total}\n📤 Signals Sent: {signals_sent}\n⏱️ Time: {duration:.2f} sec")

    summary = (
        f"✅ 1h Futures Scan Complete\n"
        f"Total Symbols: {total}\n"
        f"Signals Sent: {signals_sent}\n"
        f"Time: {duration:.2f} sec"
    )
    send_telegram_message(summary)

if __name__ == "__main__":
    run_strategy()
