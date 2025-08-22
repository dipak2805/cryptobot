import requests

token = '8490094419:AAEQZNSe4JzxDRowNyscVHyjjz4clOfnp2k'
chat_id = '555707299'
message = '🚨 Test message from bot'

url = f'https://api.telegram.org/bot{token}/sendMessage'
data = {'chat_id': chat_id, 'text': message}

response = requests.post(url, data=data)
print(response.status_code)
print(response.text)
