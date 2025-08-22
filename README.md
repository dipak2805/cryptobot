# cryptobot

# 📬 Sending Telegram Messages Using Python

This guide explains how to send messages to Telegram using Python. It includes bot creation, obtaining your chat ID, and a working example.

## 🔧 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow instructions:
   - Enter a name for your bot
   - Choose a unique username (must end in `bot`, like `mysignal_bot`)
3. After setup, you will get a **bot token** like:
   ```
   123456789:AAEkjlsdfKJlsdfl234kjLJLKJasdfLK
   ```
   Save this — it's your **TELEGRAM_TOKEN**

## 👤 2. Get Your Telegram Chat ID

1. Go to this URL in your browser (replace `<TOKEN>` with your bot token):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
2. In Telegram, send a message (e.g., `/start`) to your bot.
3. Refresh the browser page. You’ll see a JSON response like:
   ```json
   {
     "message": {
       "chat": {
         "id": 123456789,
         ...
       }
     }
   }
   ```
4. Copy the `id` — this is your **TELEGRAM_CHAT_ID**

## 💬 3. Python Script to Send Message with Date/Time (SGT)

Install dependencies:

```bash
pip install requests pytz
```

Then use this script:

```python
import requests
from datetime import datetime
import pytz

# --- CONFIG ---
TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN'
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'

# --- Get Singapore Time (UTC+8) ---
def get_singapore_time():
    tz = pytz.timezone("Asia/Singapore")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

# --- Send Telegram Message ---
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Telegram send error: {e}")

# --- Usage Example ---
msg = f"📡 Signal Triggered!\nDate/Time (SGT): {get_singapore_time()}"
send_telegram_message(msg)
```

## ✅ Example Output

```
📡 Signal Triggered!
Date/Time (SGT): 2025-07-27 18:15:23
```

## 🛡️ Notes

- Users must start the bot once to receive messages.
- Don’t share your token publicly.
- Be mindful of Telegram’s rate limits (about 20 messages per minute per bot).

---

# 📈 Crypto RSI + EMA21 Screener with ATR & Telegram Alerts (1-binance-crypto-usdt-rsi-ema.py)


**This script takes USDT pairs input from usdt_pairs.txt**

**The this Python script scans Binance USDT pairs for signals using:**

- ✅ RSI (14) between **40–60** and **rising**
- ✅ **EMA21 crossover**: previous candle low < EMA21 and current close > EMA21
- ✅ **ATR(14)** rising
- ✅ 24h **USDT Volume > 20M**
- ✅ 24h **Price Change > -5%**
- ✅ Sends matching signals to **Telegram**.

---

# 📊 Crypto Signal Screener – 15-Minute Strategy (Binance Spot- 2-binance-crypto-usdt-15m-long.py)

This script takes USDT pairs input from usdt_pairs.txt

This script scans Binance **USDT trading pairs** on the **15-minute timeframe** for a specific candlestick and RSI-based strategy, sending trade alerts to **Telegram** when all conditions are met.
## ✅ Strategy Conditions
For a symbol to trigger a signal:
1. **Current candle must be green**  
   (i.e. `close > open`)
2. **Middle candle (previous) low is lower** than both:
   - current candle low
   - candle before previous (prev2) low
3. If **middle candle is green**:  
   `current close > middle open`
4. If **middle candle is red**:  
   `current close > middle close`
5. **RSI (14)** on 15m timeframe:
   - `RSI < 50`
   - `RSI > 30`
6. **24h Quote Volume > $20 million**

## 📤 Telegram Alerts
When a signal is found, the bot sends a formatted message to a Telegram chat:

---

# 🟢 Binance RSI Screener with Telegram Alerts (3-binance-crypto-usdt-rsi-30-50.py)

This script takes USDT pairs input from usdt_pairs.txt

This Python script scans Binance **USDT trading pairs** based on **RSI conditions** and sends alerts to **Telegram** when a potential trading signal is detected.

## 📌 Features

- Screens selected USDT pairs using **15-minute RSI strategy**
- Alerts if:
  - RSI is between **40–50**
  - RSI is **increasing**
  - 24H volume is **above $30 million**
  - 24H price change is **above -5%**
- Sends **Telegram alerts** for up to 5 signals
- Reports:
  - Total pairs processed
  - Signals sent
  - Total time taken
