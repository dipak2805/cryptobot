import requests

def get_top_usdt_gainers():
    base_url = "https://api.binance.com"

    # Get all symbols
    exchange_info = requests.get(f"{base_url}/api/v3/exchangeInfo").json()
    symbols = exchange_info['symbols']

    # Filter only active USDT pairs
    usdt_pairs = {s['symbol'] for s in symbols if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING'}

    # Get 24hr ticker info
    ticker_data = requests.get(f"{base_url}/api/v3/ticker/24hr").json()

    # Filter only USDT pairs with positive price change
    filtered = []
    for data in ticker_data:
        symbol = data['symbol']
        price_change = float(data['priceChangePercent'])
        volume = float(data['quoteVolume'])  # Quote volume is in USDT

        if symbol in usdt_pairs and price_change > 0:
            filtered.append({
                'symbol': symbol,
                'last_price': float(data['lastPrice']),
                'price_change_percent': price_change,
                'quote_volume': volume
            })

    # Sort by volume descending and take top 20
    top_20 = sorted(filtered, key=lambda x: x['quote_volume'], reverse=True)[:20]

    print(f"\nTop 20 USDT Pairs with Positive 24h Change by Volume\n{'='*55}")
    for item in top_20:
        print(f"Symbol     : {item['symbol']}")
        print(f"Last Price : {item['last_price']}")
        print(f"Change %   : {item['price_change_percent']}%")
        print(f"24h Volume : ${item['quote_volume']:.2f}")
        print('-' * 55)

if __name__ == "__main__":
    get_top_usdt_gainers()
