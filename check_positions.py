#!/usr/bin/env python3
import os
import requests
import sys

sys.path.insert(0, '/Users/farzad/polyagent')
from agents.polymarket.polymarket import Polymarket

pm = Polymarket()
address = pm.get_address_for_private_key()
print(f'Address: {address}')

url = f'https://data-api.polymarket.com/positions?user={address.lower()}'
resp = requests.get(url, timeout=10)
if resp.status_code == 200:
    positions = resp.json()
    print(f'Found {len(positions)} positions')
    for pos in positions:
        title = pos.get('title', 'Unknown')
        size = pos.get('size', 0)
        value = pos.get('value', 0)
        condition_id = pos.get('conditionId', '')
        print(f'  {title[:50]}... Size: {size:.2f}, Value: ${value:.2f}, Condition: {condition_id[:10]}...')
        if '0x7c066c38aa' in condition_id:
            print(f'  *** FOUND SOLANA MARKET: {pos}')
else:
    print(f'Failed to get positions: {resp.status_code}')