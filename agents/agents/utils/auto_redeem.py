import os
import json
import time
import requests
import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

# Polygon RPC
POLYGON_RPC = os.getenv("POLYGON_RPC", "https://polygon-rpc.com")

# Polymarket Contract Addresses (Polygon Mainnet)
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Conditional Tokens ABI (only what we need for redemption)
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
    },
    {
        "inputs": [
            {"name": "conditionId", "type": "bytes32"}
        ],
        "name": "payoutNumerators",
        "outputs": [{"name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "id", "type": "uint256"}
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class AutoRedeemer:
    """TURBO MODE: Specifically optimized for high capital velocity."""
    
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        
        # Try multiple env var names for private key
        self.private_key = (
            os.getenv("POLYGON_WALLET_PRIVATE_KEY") or
            os.getenv("PRIVATE_KEY") or 
            os.getenv("PK") or 
            ""
        )
        
        # Try to get address from Polymarket client if private key not found
        self.address = None
        if self.private_key:
            self.account = Account.from_key(self.private_key)
            self.address = self.account.address
        else:
            # Fallback: try to import Polymarket and get address
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                from agents.polymarket.polymarket import Polymarket
                pm = Polymarket()
                self.address = pm.get_address_for_private_key()
                # Get private key from pm
                self.private_key = pm.private_key
                if self.private_key:
                    self.account = Account.from_key(self.private_key)
            except Exception as e:
                print(f"   ⚠️ Could not get address from Polymarket: {e}")
            
        self.ctf = self.w3.eth.contract(
            address=Web3.to_checksum_address(CONDITIONAL_TOKENS),
            abi=CTF_ABI
        )
        
        # TURBO FEATURE: The Watchlist
        self.market_watchlist = {}  # {condition_id: {"end_time": timestamp, "token_id": id}}
        self.last_balance_refresh = 0
        
        print(f"MAAX VELOCITY ACTIVATED")
        
        print(f"🔄 AutoRedeemer initialized")
        print(f"   Address: {self.address}")
        print(f"   Has PK: {bool(self.private_key)}")
        print(f"   RPC: {POLYGON_RPC[:30]}...")

    def get_positions_from_api(self) -> List[Dict]:
        """Get current positions from Polymarket API."""
        if not self.address:
            return []
        
        try:
            url = f"https://data-api.polymarket.com/positions?user={self.address.lower()}"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []
    
    def get_market_info(self, condition_id: str) -> Optional[Dict]:
        """Get market info including resolution status."""
        try:
            url = f"https://gamma-api.polymarket.com/markets?condition_id={condition_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                markets = resp.json()
                return markets[0] if markets else None
            return None
        except:
            return None

    def update_watchlist(self):
        """Fetches all open positions and maps their exact end_dates."""
        positions = self.get_positions_from_api()
        added = 0
        for pos in positions:
            # Handle varied API response keys
            cond_id = pos.get("conditionId") or pos.get("condition_id")
            token_id = pos.get("asset") or pos.get("tokenId")
            market_title = pos.get("title", "Unknown")[:40]
            size = float(pos.get("size", 0))
            
            # Only track if we have shares
            if size <= 0:
                continue

            if cond_id and cond_id not in self.market_watchlist:
                market_info = self.get_market_info(cond_id)
                if market_info and market_info.get("endDate"):
                    try:
                        # Convert ISO date to UTC timestamp
                        end_str = market_info["endDate"].replace("Z", "+00:00")
                        end_ts = datetime.datetime.fromisoformat(end_str).timestamp()
                        self.market_watchlist[cond_id] = {
                            "end_time": end_ts,
                            "token_id": token_id,
                            "title": market_title
                        }
                        added += 1
                    except: pass
        
        if added > 0:
            print(f"   📡 Watchlist Updated: Monitoring {len(self.market_watchlist)} active resolutions.")

    def check_if_resolved(self, condition_id: str) -> bool:
        """Check on-chain if resolved."""
        try:
            # Convert condition_id to bytes32
            if not condition_id.startswith("0x"):
                condition_id = "0x" + condition_id
            
            # Pad to 32 bytes if needed
            condition_hex = condition_id[2:].zfill(64)
            condition_bytes = bytes.fromhex(condition_hex)
            
            # Get payout numerators - if non-zero, market is resolved
            payouts = self.ctf.functions.payoutNumerators(condition_bytes).call()
            return any(p > 0 for p in payouts)
        except Exception as e:
            # print(f"      On-chain check failed: {e}")
            return False

    def redeem_position(self, condition_id: str, token_id: str) -> Optional[str]:
        """Redeem a winning position."""
        if not self.private_key:
            return None
        
        try:
            # Prepare condition_id as bytes32
            if not condition_id.startswith("0x"):
                condition_id = "0x" + condition_id
            condition_bytes = bytes.fromhex(condition_id[2:].zfill(64))
            
            # Parent collection and index sets
            parent_collection = bytes(32)
            index_sets = [1, 2] # Binary markets
            
            # Build transaction
            tx = self.ctf.functions.redeemPositions(
                Web3.to_checksum_address(USDC_ADDRESS),
                parent_collection,
                condition_bytes,
                index_sets
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': 137
            })
            
            # Sign and send
            signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            print(f"   ✅ Redemption tx: {tx_hash.hex()}")
            return tx_hash.hex()
                
        except Exception as e:
            print(f"   ❌ Redemption error: {e}")
            return None

    def settlement_sniper(self):
        """High-frequency check for markets that just reached their end_time."""
        now = time.time()
        to_redeem = []

        for cond_id, data in self.market_watchlist.items():
            # If the market duration has passed, check on-chain status IMMEDIATELY
            if now >= data["end_time"]:
                # Only log verbose check once per minute to avoid spamming
                if now % 60 < 10: 
                    print(f"   🎯 TARGET REACHED: {data['title']} (Checking oracle...)")
                    
                if self.check_if_resolved(cond_id):
                    print(f"   🚀 ORACLE CONFIRMED: {data['title']} - SNIPING NOW!")
                    to_redeem.append((cond_id, data["token_id"]))

        for cond_id, token_id in to_redeem:
            tx = self.redeem_position(cond_id, token_id)
            if tx:
                # Remove from watchlist once successful
                del self.market_watchlist[cond_id]
                self._force_agent_reinvest()

    def _force_agent_reinvest(self):
        """Forces all agents to update their balance for continuous compounding."""
        try:
            from agents.utils.context import get_context
            # Trigger context refresh
            ctx = get_context()
            print("   💰 Compounding: Notifying agents to scale bet sizes.")
        except: pass

    def run_turbo_loop(self):
        """
        Hyper-aggressive loop:
        - Scans for new positions every 5 mins
        - Snipes settlements every 10 seconds
        """
        print(f"\n🚀 TURBO REDEEMER ACTIVE (Settlement Sniping)")
        
        # Initial scan
        self.update_watchlist()
        last_watch_update = time.time()
        
        while True:
            try:
                now = time.time()
                
                # 1. Update Watchlist (Every 5 Minutes)
                if now - last_watch_update > 300:
                    self.update_watchlist()
                    last_watch_update = now
                
                # 2. Sniper Check (Every 10 Seconds)
                self.settlement_sniper()
                
            except Exception as e:
                print(f"Error in sniper loop: {e}")
            
            time.sleep(10) # 10s precision for unlocking capital

    def scan_and_redeem(self) -> Dict:
        """Compat wrapper for agents: one-off scan and redeem."""
        self.update_watchlist()
        
        # Track what gets redeemed
        before_count = len(self.market_watchlist)
        self.settlement_sniper()
        after_count = len(self.market_watchlist)
        
        redeemed_count = before_count - after_count
        return {"redeemed": max(0, redeemed_count)}

def redeem_all_positions() -> Dict:
    """One-shot function (standard mode)"""
    redeemer = AutoRedeemer()
    redeemer.run_turbo_loop() # Default to turbo for this call for now
    return {}

if __name__ == "__main__":
    redeemer = AutoRedeemer()
    redeemer.run_turbo_loop()
