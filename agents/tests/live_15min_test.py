#!/usr/bin/env python3
"""
LIVE 15-MINUTE CRYPTO SCALPER TEST
Full Lifecycle: Discovery -> Trade -> Settlement -> Redemption

Places $1.00 trades on BTC, ETH, SOL, XRP in active 15-minute 'Up or Down' markets.
Uses Gnosis Safe proxy wallet for all operations.
Monitors settlement and auto-redeems positions.
"""

import os
import sys
import json
import time
import requests
import datetime
from collections import defaultdict
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
    sys.exit(1)

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

# Trading Parameters
TRADE_SIZE_USD = 1.00
REQUIRED_FEE_BPS = 1000
PROXY_ADDRESS = "0xdb1f88Ab5B531911326788C018D397d352B7265c"

# Assets to trade
TARGET_ASSETS = {
    'btc': 'bitcoin',
    'eth': 'ethereum',
    'sol': 'solana',
    'xrp': 'xrp'
}

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def print_separator(title: str = ""):
    """Print a visual separator"""
    if title:
        print(f"\n{'='*80}")
        print(f"🎯 {title.upper()}")
        print('='*80)
    else:
        print('-' * 80)

def get_fee_bps(token_id):
    """Fetch fee rate for a token"""
    try:
        url = "https://clob.polymarket.com/fee-rate"
        resp = requests.get(url, params={"token_id": token_id}, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return int(data.get("base_fee", 0))  # API returns "base_fee", not "fee_rate_bps"
        return 0
    except:
        return 0

def discover_15min_markets(pm):
    """Discover active 15-minute crypto markets using direct API calls (no websockets)"""
    print(f"🔍 Discovering 15-minute crypto markets...")

    found_markets = []

    # Use the known working timestamps from our earlier discovery
    time_windows = [
        1768572000,  # 9:00 AM ET / 14:00 UTC (ends 14:15)
        1768572900,  # 9:15 AM ET / 14:15 UTC (ends 14:30)
        1768573800,  # 9:30 AM ET / 14:30 UTC (ends 14:45)
    ]

    print(f"   ⏰ Checking time windows: {[datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime('%H:%M') for ts in time_windows]}")

    # Check each asset for each time window
    for asset_code, asset_name in TARGET_ASSETS.items():
        for timestamp in time_windows:
            try:
                slug = f"{asset_code}-updown-15m-{timestamp}"
                params = {"slug": slug}

                print(f"   🔍 Checking {asset_code.upper()} @ {datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).strftime('%H:%M')}")

                resp = requests.get("https://gamma-api.polymarket.com/events", params=params, timeout=5)
                events = resp.json()

                if events:
                    event = events[0]
                    markets = event.get("markets", [])

                    print(f"      📊 Event has {len(markets)} markets")

                    for m in markets:
                        accepting = m.get('acceptingOrders')
                        active = m.get('active')
                        end_date = m.get('endDate')

                        print(f"      Market: acceptingOrders={accepting}, active={active}, endDate={end_date}")

                        if not accepting:
                            print("         ❌ Not accepting orders")
                            continue

                        clob_ids = m.get("clobTokenIds", [])
                        if isinstance(clob_ids, str):
                            try:
                                import json
                                clob_ids = json.loads(clob_ids)
                            except Exception as e:
                                print(f"         ❌ Failed to parse clobTokenIds: {e}")
                                continue

                        if not clob_ids or len(clob_ids) != 2:
                            print(f"         ❌ Invalid clobTokenIds: {clob_ids}")
                            continue

                        # Verify fee rate
                        yes_token_id = clob_ids[0]
                        fee_bps = get_fee_bps(yes_token_id)
                        print(f"         💰 Fee rate for token {yes_token_id[:8]}...: {fee_bps} bps")

                        if fee_bps != REQUIRED_FEE_BPS:
                            print(f"         ❌ Wrong fee rate (expected {REQUIRED_FEE_BPS}, got {fee_bps})")
                            continue

                        print(f"         ✅ VALID MARKET FOUND!")

                        found_markets.append({
                            "asset_code": asset_code,
                            "asset_name": asset_name,
                            "market_id": m["id"],
                            "question": m["question"],
                            "up_token": clob_ids[0],
                            "down_token": clob_ids[1],
                            "end_date": m.get("endDate", ""),
                            "created_at": m.get("createdAt", ""),
                            "event_slug": slug,
                            "fee_bps": fee_bps
                        })
                        break  # Take first valid market for this asset

                else:
                    print(f"      ❌ No events found for slug {slug}")

            except Exception as e:
                print(f"      ❌ Error checking {asset_code}@{timestamp}: {e}")
                continue

    print(f"   🎯 Found {len(found_markets)} valid 15-minute markets.")
    return found_markets

def place_trade(pm, market, direction="UP"):
    """Place a $1.00 trade on the specified market"""
    print(f"   💸 Placing $1.00 {direction} trade on {market['asset_name'].upper()}...")

    token_id = market['up_token'] if direction == "UP" else market['down_token']

    try:
        # Get current price for sizing
        try:
            price_data = pm.get_current_price(token_id)
            current_price = price_data[0] if price_data[0] > 0 else 0.5
        except:
            current_price = 0.5  # Fallback

        # Calculate size for $1.00
        size_shares = TRADE_SIZE_USD / current_price

        print(".4f")

        # Place limit order at current price (should match)
        # Note: fee_rate_bps might be causing base64 encoding issues, try without it first
        try:
            order_response = pm.place_limit_order(
                token_id=token_id,
                price=current_price,
                size=size_shares,
                side="BUY",
                fee_rate_bps=market['fee_bps']
            )
        except:
            print("   ⚠️ Retrying without fee_rate_bps...")
            order_response = pm.place_limit_order(
                token_id=token_id,
                price=current_price,
                size=size_shares,
                side="BUY"
            )

        print_separator("RAW ORDER RESPONSE")
        print("📄 Complete JSON Response from place_limit_order():")
        print(json.dumps(order_response, indent=2))

        if order_response.get("success"):
            order_id = order_response.get("orderID") or order_response.get("order_id")
            if order_id:
                print(f"✅ Order placed successfully! Order ID: {order_id}")
                return {
                    "order_id": order_id,
                    "market": market,
                    "direction": direction,
                    "size": size_shares,
                    "price": current_price,
                    "token_id": token_id,
                    "response": order_response
                }

        print("❌ Order placement failed!")
        return None

    except Exception as e:
        print(f"❌ Trade execution failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def wait_for_settlement(trades):
    """Monitor trades and wait for settlement"""
    print_separator("MONITORING SETTLEMENT")

    if not trades:
        print("❌ No trades to monitor")
        return

    print(f"⏳ Monitoring {len(trades)} trades for settlement...")

    # Group trades by end time
    end_times = {}
    for trade in trades:
        end_date = trade['market']['end_date']
        if end_date not in end_times:
            end_times[end_date] = []
        end_times[end_date].append(trade)

    print(f"📅 Settlement times:")
    for end_time, trade_list in end_times.items():
        assets = [t['market']['asset_name'].upper() for t in trade_list]
        print(f"   {end_time}: {', '.join(assets)}")

    # Wait for each settlement time
    settled_trades = []
    for end_time_str, trade_list in end_times.items():
        try:
            if end_time_str.endswith('Z'):
                end_time = datetime.datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            else:
                end_time = datetime.datetime.fromisoformat(end_time_str + '+00:00')

            now = datetime.datetime.now(end_time.tzinfo)

            if now >= end_time:
                print(f"🎯 {end_time_str} already passed - checking settlement...")
                settled_trades.extend(trade_list)
            else:
                wait_seconds = (end_time - now).total_seconds()
                print(f"⏰ Waiting {wait_seconds:.0f} seconds for {end_time_str} settlement...")

                # Wait in 30-second intervals
                while wait_seconds > 0:
                    time.sleep(min(30, wait_seconds))
                    wait_seconds -= 30
                    remaining_mins = wait_seconds / 60
                    if remaining_mins > 0:
                        print(f"   ⏳ {remaining_mins:.1f} minutes remaining...")

                print(f"🎯 {end_time_str} should now be settled!")
                settled_trades.extend(trade_list)

        except Exception as e:
            print(f"❌ Error waiting for settlement: {e}")
            settled_trades.extend(trade_list)  # Assume settled on error

    return settled_trades

def redeem_positions(pm, settled_trades):
    """Redeem settled positions via Gnosis Safe"""
    print_separator("REDEMPTION VIA GNOSIS SAFE")

    if not settled_trades:
        print("❌ No settled trades to redeem")
        return []

    redemption_hashes = []

    for trade in settled_trades:
        try:
            token_id = trade['token_id']
            asset_name = trade['market']['asset_name']

            print(f"🔄 Redeeming {asset_name.upper()} position (Token: {token_id[:8]}...)")

            # Use the redemption logic from full_lifecycle_test.py
            redemption_tx = redeem_via_gnosis_safe(token_id, f"{asset_name} 15-min market")

            if redemption_tx:
                print(f"✅ Redemption successful! TX: {redemption_tx}")
                redemption_hashes.append({
                    "asset": asset_name,
                    "token_id": token_id,
                    "tx_hash": redemption_tx,
                    "trade": trade
                })
            else:
                print(f"❌ Redemption failed for {asset_name}")

        except Exception as e:
            print(f"❌ Error redeeming {asset_name}: {e}")
            import traceback
            traceback.print_exc()

    return redemption_hashes

def redeem_via_gnosis_safe(token_id, market_title):
    """Execute redemption using Gnosis Safe execTransaction"""
    print(f"🔄 Redeeming position from market: {market_title}")
    print(f"🎫 Token ID: {token_id}")

    # Gnosis Safe configuration
    PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
    POLYGON_RPC = os.getenv("POLYGON_RPC", "https://polygon-bor.publicnode.com")

    if not PRIVATE_KEY:
        print("❌ Missing POLYGON_WALLET_PRIVATE_KEY in .env")
        return None

    # Import required modules
    from web3 import Web3
    from eth_account import Account

    # Minimal ABIs for redemption
    SAFE_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "value", "type": "uint256"},
                {"internalType": "bytes", "name": "data", "type": "bytes"},
                {"internalType": "uint8", "name": "operation", "type": "uint8"},
                {"internalType": "uint256", "name": "safeTxGas", "type": "uint256"},
                {"internalType": "uint256", "name": "baseGas", "type": "uint256"},
                {"internalType": "uint256", "name": "gasPrice", "type": "uint256"},
                {"internalType": "address", "name": "gasToken", "type": "address"},
                {"internalType": "address", "name": "refundReceiver", "type": "address"},
                {"internalType": "bytes", "name": "signatures", "type": "bytes"}
            ],
            "name": "execTransaction",
            "outputs": [{"internalType": "bool", "name": "success", "type": "bool"}],
            "stateMutability": "payable",
            "type": "function"
        },
        {"inputs": [], "name": "nonce", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}
    ]

    CTF_ABI = [
        {
            "inputs": [
                {"name": "collateralToken", "type": "address"},
                {"name": "parentCollectionId", "type": "bytes32"},
                {"name": "conditionId", "type": "bytes32"},
                {"name": "indexSets", "type": "uint256[]"}
            ],
            "name": "redeemPositions",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]

    def get_safe_tx_hash(safe_address, to, value, data, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce, chain_id):
        """Calculate Gnosis Safe transaction hash"""
        DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
        domain_separator = Web3.solidity_keccak(
            ['bytes32', 'uint256', 'address'],
            [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe_address]
        )

        SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")
        data_hash = Web3.keccak(hexstr=data)

        safe_tx_hash = Web3.solidity_keccak(
            ['bytes32', 'address', 'uint256', 'bytes32', 'uint8', 'uint256', 'uint256', 'uint256', 'address', 'address', 'uint256'],
            [SAFE_TX_TYPEHASH, to, value, data_hash, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce]
        )

        return Web3.solidity_keccak(
            ['bytes1', 'bytes1', 'bytes32', 'bytes32'],
            [bytes.fromhex('19'), bytes.fromhex('01'), domain_separator, safe_tx_hash]
        )

    try:
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        account = Account.from_key(PRIVATE_KEY)

        print(f"🔑 Signer EOA: {account.address}")
        print(f"🏦 Target Proxy: {PROXY_ADDRESS}")

        proxy_contract = w3.eth.contract(address=PROXY_ADDRESS, abi=SAFE_ABI)
        ctf_contract = w3.eth.contract(address="0x4D97DCd97eC945f40cF65F87097ACe5EA0476045", abi=CTF_ABI)

        # Get positions for the proxy wallet
        print("📡 Fetching positions from proxy wallet...")
        url = f"https://data-api.polymarket.com/positions?user={PROXY_ADDRESS}"
        positions = requests.get(url, timeout=10).json()

        print(f"📊 Found {len(positions)} positions")

        # Find the position for our token
        target_position = None
        for pos in positions:
            if pos.get("asset") == token_id:
                target_position = pos
                break

        if not target_position:
            print(f"❌ No position found for token {token_id}")
            return None

        print(f"✅ Found position: {target_position.get('title', 'Unknown')}")

        # Encode redemption call
        condition_id = target_position.get("conditionId")
        if not condition_id:
            print("❌ No condition ID found")
            return None

        print(f"🔢 Condition ID: {condition_id}")

        inner_data = ctf_contract.encodeABI(
            fn_name="redeemPositions",
            args=[
                Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),  # USDC
                bytes(32),  # parentCollectionId (0)
                bytes.fromhex(condition_id[2:]),  # conditionId
                [1, 2]  # indexSets for binary market
            ]
        )

        # Get nonce
        nonce = proxy_contract.functions.nonce().call()
        print(f"🔢 Safe Nonce: {nonce}")

        # Build transaction parameters
        to = Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")  # CTF
        value = 0
        operation = 0  # Call
        safe_tx_gas = 500000
        base_gas = 0
        gas_price = 0
        gas_token = "0x0000000000000000000000000000000000000000"
        refund_receiver = "0x0000000000000000000000000000000000000000"
        chain_id = 137

        # Calculate hash and sign
        tx_hash_bytes = get_safe_tx_hash(
            PROXY_ADDRESS, to, value, inner_data, operation,
            safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver,
            nonce, chain_id
        )

        signed = w3.eth.account._sign_hash(tx_hash_bytes, private_key=PRIVATE_KEY)
        signature = signed.r.to_bytes(32, 'big') + signed.s.to_bytes(32, 'big') + signed.v.to_bytes(1, 'big')

        print("📝 Executing redemption transaction...")

        # Build and send transaction
        tx = proxy_contract.functions.execTransaction(
            to, value, inner_data, operation,
            safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver,
            signature
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'chainId': 137
        })

        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        print(f"✅ Redemption sent! TX Hash: {tx_hash.hex()}")
        print(f"🔗 View on PolygonScan: https://polygonscan.com/tx/{tx_hash.hex()}")

        # Wait for confirmation
        print("⏳ Waiting for confirmation...")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        print("🎉 Redemption confirmed!")

        return tx_hash.hex()

    except Exception as e:
        print(f"❌ Redemption failed: {e}")
        import traceback
        traceback.print_exc()
        return None

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    print_separator("LIVE 15-MINUTE CRYPTO SCALPER TEST")
    print("Full Lifecycle: Discovery -> Trade -> Settlement -> Redemption")
    print(f"Trading $1.00 on BTC, ETH, SOL, XRP using Gnosis Safe proxy")
    print(f"Proxy Address: {PROXY_ADDRESS}")
    print("="*80)

    try:
        # ========================================================================
        # 1. INITIALIZE POLYMARKET CLIENT
        # ========================================================================
        print_separator("INITIALIZATION")

        print("🔧 Initializing Polymarket client with Gnosis Safe config...")
        pm = Polymarket()

        # Verify configuration
        print("✅ Configuration:")
        print(f"   Signature Type: 2 (GNOSIS_SAFE)")
        print(f"   Funder Address: {PROXY_ADDRESS}")

        # ========================================================================
        # 2. DISCOVER MARKETS
        # ========================================================================
        print_separator("MARKET DISCOVERY")

        markets = discover_15min_markets(pm)
        if not markets:
            print("❌ No valid 15-minute markets found!")
            return

        # Group by asset
        asset_markets = {}
        for market in markets:
            asset_markets[market['asset_code']] = market

        found_assets = list(asset_markets.keys())
        print(f"📊 Found markets for: {', '.join(found_assets).upper()}")

        # ========================================================================
        # 3. PLACE TRADES
        # ========================================================================
        print_separator("TRADE EXECUTION")

        trades = []
        trade_hashes = []

        for asset_code in TARGET_ASSETS.keys():
            if asset_code in asset_markets:
                market = asset_markets[asset_code]
                trade = place_trade(pm, market, direction="UP")  # Bet UP on all

                if trade:
                    trades.append(trade)
                    trade_hashes.append({
                        "asset": market['asset_name'],
                        "order_id": trade['order_id'],
                        "tx_response": trade['response']
                    })
                else:
                    print(f"❌ Failed to place trade for {asset_code.upper()}")
            else:
                print(f"⚠️ No market found for {asset_code.upper()}")

        if not trades:
            print("❌ No trades were placed successfully!")
            return

        print_separator("TRADE SUMMARY")
        print(f"✅ Successfully placed {len(trades)} trades:")
        for trade in trades:
            asset = trade['market']['asset_name'].upper()
            order_id = trade['order_id']
            size = trade['size']
            price = trade['price']
            print(f"   {asset}: Order {order_id[:8]}... (${size*price:.2f})")

        # ========================================================================
        # 4. WAIT FOR SETTLEMENT
        # ========================================================================
        settled_trades = wait_for_settlement(trades)

        # ========================================================================
        # 5. REDEEM POSITIONS
        # ========================================================================
        print_separator("POSITION REDEMPTION")

        redemption_hashes = redeem_positions(pm, settled_trades)

        # ========================================================================
        # 6. FINAL SUMMARY
        # ========================================================================
        print_separator("FINAL SUMMARY")

        print("📊 TRADE HASHES:")
        for trade in trade_hashes:
            print(f"   {trade['asset'].upper()}: {trade['order_id']}")
            print(f"      Raw Response: {json.dumps(trade['tx_response'], indent=6)}")

        print("\n📊 REDEMPTION HASHES:")
        for redemption in redemption_hashes:
            print(f"   {redemption['asset'].upper()}: {redemption['tx_hash']}")
            print(f"      Token: {redemption['token_id']}")

        print(f"\n🎯 TEST COMPLETE: {len(trade_hashes)} trades placed, {len(redemption_hashes)} positions redeemed")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

    print_separator("TEST COMPLETE")

if __name__ == "__main__":
    main()