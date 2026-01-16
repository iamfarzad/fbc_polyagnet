#!/usr/bin/env python3
"""
Check Polymarket account access and balance
"""

import sys
import os
import requests

# Setup paths
sys.path.insert(0, '/Users/farzad/polyagent')

from agents.agents.polymarket.polymarket import Polymarket

def check_polymarket_account():
    pm = Polymarket()

    print('🔍 CHECKING POLYMARKET ACCOUNT VIA GAMMA API...')
    print('=' * 60)

    # Try to get account balance via Gamma API
    gamma_url = 'https://gamma-api.polymarket.com'

    # Check if we can get user account info
    try:
        headers = {}
        if pm.credentials and hasattr(pm.credentials, 'api_key'):
            headers['Authorization'] = f'Bearer {pm.credentials.api_key}'

        response = requests.get(f'{gamma_url}/users/me', headers=headers, timeout=10)
        print(f'Account API status: {response.status_code}')

        if response.status_code == 200:
            account_data = response.json()
            print('✅ Account data retrieved:')
            for key, value in account_data.items():
                if key in ['id', 'username', 'email', 'account']:
                    print(f'  {key}: {value}')
        else:
            print(f'Account API failed: {response.text[:200]}')

    except Exception as e:
        print(f'❌ Account check failed: {e}')

    print()
    print('🔍 CHECKING MARKET DATA ACCESS...')

    # Test market data access (this should work)
    try:
        markets_response = requests.get(f'{gamma_url}/markets?closed=false&limit=5', timeout=10)
        if markets_response.status_code == 200:
            markets = markets_response.json()
            print(f'✅ Market data access works - found {len(markets)} markets')

            # Show one market
            if markets:
                market = markets[0]
                print(f'  Sample market: {market.get("question", "")[:50]}...')
                print(f'  Volume: ${market.get("volume", 0):.0f}')
        else:
            print(f'❌ Market data failed: {markets_response.status_code}')

    except Exception as e:
        print(f'❌ Market data check failed: {e}')

if __name__ == "__main__":
    check_polymarket_account()