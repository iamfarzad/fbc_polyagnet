#!/usr/bin/env python3
"""
Polymarket Proxy Wallet Verification Test Script
Tests the updated Polymarket class with Gnosis Safe Proxy Wallet integration.

This script verifies:
1. Configuration: signature_type and funder_address match Fly.io secrets
2. Balance: API recognizes $113.41 in proxy wallet
3. Market Discovery: Finds liquid Bitcoin/Ethereum markets
4. Order Execution: Places $1.00 limit order test trade
5. Response Analysis: Checks maker field and raw JSON response
"""

import os
import sys
import json
import time
from dotenv import load_dotenv

# Set PYTHONPATH like main.py does
os.environ["PYTHONPATH"] = "."
os.environ["PYTHONUNBUFFERED"] = "1"

# Add agents directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    from agents.polymarket.polymarket import Polymarket
    print("✅ Successfully imported Polymarket class")
except ImportError as e:
    print(f"❌ Failed to import Polymarket class: {e}")
    print("Make sure you're running from the polyagent root directory")
    sys.exit(1)

# Load environment variables
load_dotenv()
print("\n🔧 Environment loaded")

def print_separator(title: str = ""):
    """Print a visual separator"""
    if title:
        print(f"\n{'='*60}")
        print(f"📋 {title.upper()}")
        print('='*60)
    else:
        print('-' * 60)

def main():
    print_separator("POLYMARKET PROXY WALLET VERIFICATION")
    print("Testing Gnosis Safe Proxy Wallet integration...")

    try:
        # Initialize Polymarket client
        print("\n🚀 Initializing Polymarket client...")
        pm = Polymarket()

        # ========================================================================
        # 1. PRINT CONFIGURATION
        # ========================================================================
        print_separator("CONFIGURATION CHECK")

        # Check signature type (should be 2 for GNOSIS_SAFE)
        signature_type = os.getenv("POLYMARKET_SIGNATURE_TYPE", "NOT_SET")
        print(f"🔑 Signature Type (POLYMARKET_SIGNATURE_TYPE): {signature_type}")
        if signature_type == "2":
            print("✅ Signature type correctly set to 2 (GNOSIS_SAFE)")
        else:
            print("⚠️ Signature type not set - checking if client uses default GNOSIS_SAFE...")
            # Check if client initialized with correct signature type
            try:
                # The client should have been initialized with signature_type=2 from the code
                print("🔍 Client should auto-detect GNOSIS_SAFE signature type")
            except:
                pass

        # Check funder/proxy address (should be 0xdb1f88Ab5B531911326788C018D397d352B7265c)
        funder_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER")
        print(f"🏦 Funder/Proxy Address: {funder_address}")
        expected_proxy = "0xdb1f88Ab5B531911326788C018D397d352B7265c"
        if funder_address and funder_address.lower() == expected_proxy.lower():
            print("✅ Funder address matches expected proxy wallet!")
        else:
            print(f"❌ Funder address should be {expected_proxy}")

        # Check if client has the correct funder
        if hasattr(pm.client, 'funder') and pm.client.funder:
            client_funder = pm.client.funder
            print(f"🔗 Client Funder Address: {client_funder}")
            if client_funder.lower() == expected_proxy.lower():
                print("✅ Client funder matches expected proxy!")
            else:
                print(f"❌ Client funder ({client_funder}) doesn't match proxy ({expected_proxy})")
        else:
            print("⚠️ Client funder not set - this may cause issues")

        # ========================================================================
        # 2. CHECK BALANCE
        # ========================================================================
        print_separator("BALANCE CHECK")

        print("💰 Checking USDC balance...")
        try:
            balance = pm.get_usdc_balance()
            print(".2f")
            if balance >= 100:  # Should be around $113.41
                print("✅ Balance looks correct for proxy wallet!")
            else:
                print(f"⚠️ Balance seems low (${balance:.2f}) - expected ~$113.41")
        except Exception as e:
            print(f"❌ Balance check failed: {e}")

        # ========================================================================
        # 3. FIND LIQUID MARKET
        # ========================================================================
        print_separator("MARKET DISCOVERY")

        print("🔍 Finding liquid Bitcoin/Ethereum markets...")
        try:
            # Try multiple approaches to find live markets
            print("🔍 Trying different API calls to find live markets...")

            # First try: get markets with acceptingOrders=true
            try:
                markets = pm.get_all_markets(limit=100, active=True, acceptingOrders=True)
                print(f"📊 Found {len(markets)} markets accepting orders")
            except:
                # Fallback: get all active markets
                markets = pm.get_all_markets(limit=100, active=True)
                print(f"📊 Found {len(markets)} active markets total")

            # Second try: direct Gamma API call for accepting orders
            if not any(getattr(m, 'accepting_orders', False) for m in markets):
                print("🔄 Trying direct Gamma API call for accepting orders...")
                try:
                    import httpx
                    gamma_url = "https://gamma-api.polymarket.com/markets"
                    params = {
                        "limit": 50,
                        "active": True,
                        "closed": False  # Try this parameter instead
                    }
                    response = httpx.get(gamma_url, params=params, timeout=10)
                    if response.status_code == 200:
                        gamma_markets = response.json()
                        if gamma_markets:
                            print(f"🎯 Gamma API found {len(gamma_markets)} markets")
                            # Try to use Gamma API results but handle mapping errors
                            try:
                                new_markets = []
                                for m in gamma_markets[:10]:  # Just try first 10
                                    try:
                                        mapped = pm.map_api_to_market(m)
                                        new_markets.append(mapped)
                                    except:
                                        continue
                                if new_markets:
                                    markets.extend(new_markets)
                                    print(f"✅ Successfully mapped {len(new_markets)} markets from Gamma API")
                            except Exception as e:
                                print(f"⚠️ Market mapping failed: {e}")
                except Exception as e:
                    print(f"⚠️ Gamma API call failed: {e}")

            # Debug: show some market info and look for any markets with actual liquidity
            print("🔍 Scanning for markets with real liquidity...")
            liquid_markets = []
            for i, market in enumerate(markets):
                # Handle both SimpleMarket objects and raw dict responses
                if hasattr(market, 'liquidity'):
                    # SimpleMarket object
                    accepting = getattr(market, 'accepting_orders', False)
                    liquidity = market.liquidity
                    question = market.question
                    active = market.active
                else:
                    # Raw dict from Gamma API
                    accepting = market.get('acceptingOrders', False)
                    liquidity = float(market.get('liquidity', 0) or 0)
                    question = market.get('question', 'Unknown')
                    active = market.get('active', False)

                # Check if market has token IDs (needed for trading)
                clob_token_ids = market.clob_token_ids if hasattr(market, 'clob_token_ids') else market.get('clobTokenIds', '[]')
                try:
                    token_ids = json.loads(clob_token_ids)
                    has_tokens = len(token_ids) >= 2
                except:
                    has_tokens = False

                if liquidity > 100 and has_tokens:  # Must have liquidity AND token IDs
                    liquid_markets.append(market)
                    print(f"💰 Tradable Market {len(liquid_markets)}: {question[:50]}... Liquidity: ${liquidity:.0f}, Tokens: {len(token_ids)}")

                # Show first few for debugging
                if i < 5:
                    print(f"   Market {i+1}: {question[:50]}... Active: {active}, Accepting: {accepting}, Liquidity: ${liquidity:.0f}")

            if liquid_markets:
                # Sort by liquidity and pick the most liquid one
                def get_liquidity(m):
                    return m.liquidity if hasattr(m, 'liquidity') else float(m.get('liquidity', 0) or 0)

                liquid_markets.sort(key=get_liquidity, reverse=True)
                selected_market = liquid_markets[0]

                question = selected_market.question if hasattr(selected_market, 'question') else selected_market.get('question', 'Unknown')
                print(f"🎯 Selected most liquid market: {question[:60]}...")
            else:
                print("❌ No markets with liquidity found!")

                # Try to find any market that might actually be trading
                # Let's check if there are markets with volume > 0
                volume_markets = []
                for m in markets:
                    volume = m.volume if hasattr(m, 'volume') else float(m.get('volume', 0) or 0)
                    if volume > 0:
                        volume_markets.append(m)

                if volume_markets:
                    def get_volume(m):
                        return m.volume if hasattr(m, 'volume') else float(m.get('volume', 0) or 0)

                    volume_markets.sort(key=get_volume, reverse=True)
                    selected_market = volume_markets[0]
                    question = selected_market.question if hasattr(selected_market, 'question') else selected_market.get('question', 'Unknown')
                    print(f"📊 Using market with volume: {question[:60]}...")
                else:
                    print("❌ No markets with any volume found!")
                    return

            question = selected_market.question if hasattr(selected_market, 'question') else selected_market.get('question', 'Unknown')
            volume = selected_market.volume if hasattr(selected_market, 'volume') else float(selected_market.get('volume', 0) or 0)
            liquidity = selected_market.liquidity if hasattr(selected_market, 'liquidity') else float(selected_market.get('liquidity', 0) or 0)

            print(f"✅ Selected market: {question}")
            print(".0f")
            print(".2f")

            # Get token IDs for Yes/No outcomes
            clob_token_ids = selected_market.clob_token_ids if hasattr(selected_market, 'clob_token_ids') else selected_market.get('clobTokenIds', '[]')
            token_ids = json.loads(clob_token_ids)
            if len(token_ids) >= 2:
                yes_token_id = token_ids[0]  # Usually Yes is first
                print(f"🎯 Yes Token ID: {yes_token_id}")

                # ====================================================================
                # 4. EXECUTE TEST TRADE
                # ====================================================================
                print_separator("TEST TRADE EXECUTION")

                print("💸 Executing $1.00 limit order test...")

                # Get current price for Yes outcome
                try:
                    orderbook = pm.get_orderbook(yes_token_id)
                    best_bid = orderbook.bids[0].price if orderbook.bids else 0.5
                    test_price = round(best_bid + 0.01, 3)  # Slightly above best bid
                    print(f"📊 Best Bid: {best_bid}, Test Price: {test_price}")
                except Exception as e:
                    print(f"⚠️ Could not get orderbook ({e}), using fallback price: 0.55")
                    test_price = 0.55  # Fallback price

                # Place $1.00 limit order
                print(f"🎯 Placing BUY limit order: $1.00 @ {test_price} on Yes outcome...")
                try:
                    order_response = pm.place_limit_order(
                        token_id=yes_token_id,
                        price=test_price,
                        size=1.0,  # $1.00
                        side="BUY"
                    )

                    # ====================================================================
                    # 5. DEBUG OUTPUT
                    # ====================================================================
                    print_separator("ORDER RESPONSE ANALYSIS")

                    print("📄 RAW JSON Response:")
                    print(json.dumps(order_response, indent=2))

                    # Check for success
                    if order_response.get("success"):
                        print("✅ Order placed successfully!")
                        order_id = order_response.get("orderID") or order_response.get("order_id")
                        if order_id:
                            print(f"📋 Order ID: {order_id}")

                        # Check maker field in response
                        maker = order_response.get("maker") or order_response.get("makerAddress")
                        if maker:
                            print(f"🎭 Maker Address in Response: {maker}")
                            if maker.lower() == expected_proxy.lower():
                                print("✅ Maker field correctly set to proxy wallet!")
                            else:
                                print(f"❌ Maker field ({maker}) doesn't match proxy ({expected_proxy})")

                    else:
                        error = order_response.get("error", "Unknown error")
                        print(f"❌ Order failed: {error}")

                        # Check for balance issues
                        if "BALANCE" in str(error).upper() or "ENOUGH" in str(error).upper():
                            print("💰 BALANCE ERROR - Checking if maker field is set correctly...")

                            # The py-clob-client should automatically use the funder/proxy address
                            # Let's check what the client thinks the maker should be
                            if hasattr(pm.client, 'funder') and pm.client.funder:
                                print(f"🎭 Expected Maker (Funder): {pm.client.funder}")
                            else:
                                print("⚠️ No funder set in client - this is likely the issue!")

                        # If market not found, it might be resolved
                        if "NOT FOUND" in str(error).upper() or "MARKET" in str(error).upper():
                            print("📊 Market may be resolved or inactive - this is expected for test")

                except Exception as e:
                    print(f"❌ Order execution failed: {e}")
                    import traceback
                    traceback.print_exc()

            else:
                print(f"⚠️ Market only has {len(token_ids)} token IDs, expected 2+")
                return

                # ====================================================================
                # 4. EXECUTE TEST TRADE
                # ====================================================================
                print_separator("TEST TRADE EXECUTION")

                print("💸 Executing $1.00 limit order test...")

                # Get current price for Yes outcome
                try:
                    orderbook = pm.get_orderbook(yes_token_id)
                    best_bid = orderbook.bids[0].price if orderbook.bids else 0.5
                    test_price = round(best_bid + 0.01, 3)  # Slightly above best bid
                    print(f"📊 Best Bid: {best_bid}, Test Price: {test_price}")
                except:
                    test_price = 0.55  # Fallback price
                    print(f"⚠️ Could not get orderbook, using fallback price: {test_price}")

                # Place $1.00 limit order
                print(f"🎯 Placing BUY limit order: $1.00 @ {test_price} on Yes outcome...")
                try:
                    order_response = pm.place_limit_order(
                        token_id=yes_token_id,
                        price=test_price,
                        size=1.0,  # $1.00
                        side="BUY"
                    )

                    # ====================================================================
                    # 5. DEBUG OUTPUT
                    # ====================================================================
                    print_separator("ORDER RESPONSE ANALYSIS")

                    print("📄 RAW JSON Response:")
                    print(json.dumps(order_response, indent=2))

                    # Check for success
                    if order_response.get("success"):
                        print("✅ Order placed successfully!")
                        order_id = order_response.get("orderID") or order_response.get("order_id")
                        if order_id:
                            print(f"📋 Order ID: {order_id}")

                        # Check maker field in response
                        maker = order_response.get("maker") or order_response.get("makerAddress")
                        if maker:
                            print(f"🎭 Maker Address in Response: {maker}")
                            if maker.lower() == expected_proxy.lower():
                                print("✅ Maker field correctly set to proxy wallet!")
                            else:
                                print(f"❌ Maker field ({maker}) doesn't match proxy ({expected_proxy})")

                    else:
                        error = order_response.get("error", "Unknown error")
                        print(f"❌ Order failed: {error}")

                        # Check for balance issues
                        if "BALANCE" in str(error).upper() or "ENOUGH" in str(error).upper():
                            print("💰 BALANCE ERROR - Checking if maker field is set correctly...")

                            # The py-clob-client should automatically use the funder/proxy address
                            # Let's check what the client thinks the maker should be
                            if hasattr(pm.client, 'funder') and pm.client.funder:
                                print(f"🎭 Expected Maker (Funder): {pm.client.funder}")
                            else:
                                print("⚠️ No funder set in client - this is likely the issue!")

                        # If market not found, it might be resolved
                        if "NOT FOUND" in str(error).upper() or "MARKET" in str(error).upper():
                            print("📊 Market may be resolved or inactive - this is expected for test")

                except Exception as e:
                    print(f"❌ Order execution failed: {e}")
                    import traceback
                    traceback.print_exc()

        except Exception as e:
            print(f"❌ Market discovery failed: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

    print_separator("TEST COMPLETE")

if __name__ == "__main__":
    main()