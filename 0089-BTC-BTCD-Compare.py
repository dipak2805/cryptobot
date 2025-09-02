import requests
import os
import json
from datetime import datetime

# ====== CONFIG ======
TELEGRAM_BOT_TOKEN = '8490094419:AAHiq6NKVyogWirW8byVT3125XMO-d2ZA1s'
TELEGRAM_CHAT_ID = '555707299'
BINANCE_INTERVAL = "1h"   # Can be '15m','1h','4h','1d'
STATE_FILE = "dominance_state.json"

# ====== HELPER FUNCTIONS ======
def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram error:", e)

def get_btc_price_change():
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={BINANCE_INTERVAL}&limit=2"
    data = requests.get(url).json()
    prev_close = float(data[0][4])
    last_close = float(data[1][4])
    if last_close > prev_close: return "up"
    elif last_close < prev_close: return "down"
    else: return "flat"

def get_btc_dominance_change():
    url = "https://api.coingecko.com/api/v3/global"
    data = requests.get(url).json()
    btc_dominance = data["data"]["market_cap_percentage"]["btc"]

    # Load last saved dominance
    last_dom = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            last_dom = json.load(f).get("btc_dominance")

    # Save new dominance
    with open(STATE_FILE, "w") as f:
        json.dump({"btc_dominance": btc_dominance}, f)

    if last_dom is None:
        return "flat"

    if btc_dominance > last_dom: return "up"
    elif btc_dominance < last_dom: return "down"
    else: return "flat"

def market_outcome(price_dir, dom_dir):
    if price_dir == "up" and dom_dir == "up":
        return "BTC Season: Bitcoin rally, alts underperform."
    if price_dir == "up" and dom_dir == "down":
        return "Altseason: BTC up, but alts pumping harder.Altcoins outperform"
    if price_dir == "down" and dom_dir == "up":
        return "Bearish for alts: BTC down, alts crash harder."
    if price_dir == "down" and dom_dir == "down":
        return "Late Bear: Both weak, money may move to stables."
    if price_dir == "flat" and dom_dir == "up":
        return "Dominance rising while BTC flat → capital consolidating into BTC.Good time to stack BTC. Avoid alts"
    if price_dir == "flat" and dom_dir == "down":
        return "Dominance falling while BTC flat → capital rotating to alts.Accumulate alts"
    return "Mixed/Neutral: No clear signal."

def get_arrow(direction):
    if direction == "up":
        return "🟢⬆️"
    elif direction == "down":
        return "🔴⬇️"
    else:
        return "➖"

# ====== MAIN SCRIPT ======
if __name__ == "__main__":
    price_dir = get_btc_price_change()
    dom_dir = get_btc_dominance_change()

    outcome = market_outcome(price_dir, dom_dir)

    # Add arrows
    price_arrow = get_arrow(price_dir)
    dom_arrow = get_arrow(dom_dir)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        f"📊 <b>BTC & Dominance Update</b>\n"
        f"⏰ {timestamp}\n\n"
        f"💰 BTC Price: {price_dir.upper()} {price_arrow}\n"
        f"📈 BTC Dominance: {dom_dir.upper()} {dom_arrow}\n\n"
        f"🔮 Outcome: {outcome}"
    )

    # Print to console
    print(message.replace("<b>", "").replace("</b>", ""))

    # Send Telegram alert
    send_telegram_message(message)
