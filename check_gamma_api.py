#!/usr/bin/env python3
"""
Check Gamma API Raw JSON Response
Shows the actual markets returned by Polymarket Gamma API
"""

import requests
import json

def main():
    print("🔍 Fetching raw JSON from Polymarket Gamma API...")
    print("="*80)

    # Check 15-minute crypto markets (tag_id=1006)
    print("\n📊 15-Minute Crypto Markets (tag_id=1006):")
    gamma_url = "https://gamma-api.polymarket.com/markets"
    params = {
        "limit": 50,
        "active": True,
        "tag_id": 1006  # 15-Min Crypto tag
    }

    try:
        response = requests.get(gamma_url, params=params, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"URL: {response.url}")

        if response.status_code == 200:
            markets = response.json()
            print(f"Count: {len(markets)} markets")
            print("\nRAW JSON:")
            print(json.dumps(markets, indent=2))

            # Analyze the markets
            print(f"\n{'='*50}")
            print("ANALYSIS:")
            for i, market in enumerate(markets):
                question = market.get('question', 'Unknown')
                active = market.get('active', False)
                accepting_orders = market.get('acceptingOrders', False)
                volume = market.get('volume', 0)
                clob_token_ids = market.get('clobTokenIds', [])

                print(f"\nMarket {i+1}:")
                print(f"  Question: {question}")
                print(f"  Active: {active}")
                print(f"  Accepting Orders: {accepting_orders}")
                print(f"  Volume: ${volume}")
                print(f"  Token IDs: {len(clob_token_ids)} found")

        else:
            print(f"❌ Failed: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Error: {e}")

    print(f"\n{'='*80}")

    # Also check all active markets
    print("\n📊 All Active Markets (first 10):")
    try:
        params_all = {"limit": 10, "active": True}
        response_all = requests.get(gamma_url, params=params_all, timeout=10)

        if response_all.status_code == 200:
            all_markets = response_all.json()
            print(f"Status: {response_all.status_code}")
            print(f"Count: {len(all_markets)} markets")
            print("\nRAW JSON:")
            print(json.dumps(all_markets, indent=2))
        else:
            print(f"❌ Failed: {response_all.status_code}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()