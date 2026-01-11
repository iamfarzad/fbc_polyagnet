"""
Auto-Redeemer for Polymarket Positions

Automatically redeems winning positions from resolved markets.
Runs periodically to convert winning shares to USDC.
"""

import os
import json
import time
import requests
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
    """Automatically redeems winning Polymarket positions."""
    
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
    
    def check_if_resolved(self, condition_id: str) -> bool:
        """Check if a market condition is resolved on-chain."""
        try:
            # Convert condition_id to bytes32
            if not condition_id.startswith("0x"):
                condition_id = "0x" + condition_id
            
            condition_bytes = bytes.fromhex(condition_id[2:])
            
            # Get payout numerators - if non-zero, market is resolved
            payouts = self.ctf.functions.payoutNumerators(condition_bytes).call()
            return any(p > 0 for p in payouts)
        except Exception as e:
            print(f"Error checking resolution: {e}")
            return False
    
    def redeem_position(self, condition_id: str, token_id: str) -> Optional[str]:
        """
        Redeem a winning position.
        
        Args:
            condition_id: The market condition ID
            token_id: The position token ID
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        if not self.private_key:
            print("No private key - cannot redeem")
            return None
        
        try:
            # Prepare condition_id as bytes32
            if not condition_id.startswith("0x"):
                condition_id = "0x" + condition_id
            condition_bytes = bytes.fromhex(condition_id[2:].zfill(64))
            
            # Parent collection is typically 0 for binary markets
            parent_collection = bytes(32)  # 0x0...0
            
            # Index sets: [1, 2] for YES and NO outcomes
            # We redeem both - the losing side will just return 0
            index_sets = [1, 2]
            
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
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if receipt['status'] == 1:
                print(f"   ✅ Redemption confirmed!")
                return tx_hash.hex()
            else:
                print(f"   ❌ Redemption failed")
                return None
                
        except Exception as e:
            print(f"   ❌ Redemption error: {e}")
            return None
    
    def scan_and_redeem(self) -> Dict:
        """
        Scan all positions and redeem any from resolved markets.
        
        Returns:
            Summary of redemption results
        """
        print(f"\n🔄 Scanning for redeemable positions...")
        
        positions = self.get_positions_from_api()
        print(f"   Found {len(positions)} positions")
        
        results = {
            "scanned": len(positions),
            "redeemed": 0,
            "already_redeemed": 0,
            "not_resolved": 0,
            "errors": 0
        }
        
        redeemed_conditions = set()
        
        for pos in positions:
            try:
                # Get condition ID from the position
                # Position structure varies - try different fields
                condition_id = pos.get("conditionId") or pos.get("condition_id")
                token_id = pos.get("asset") or pos.get("tokenId")
                market_title = pos.get("title", "Unknown")[:40]
                size = float(pos.get("size", 0))
                value = float(pos.get("currentValue", 0))
                
                if not condition_id:
                    continue
                
                # Skip if already processed this condition
                if condition_id in redeemed_conditions:
                    continue
                
                # Skip if no shares
                if size <= 0:
                    continue
                
                # Check if position is worthless (already resolved as loss)
                if value <= 0.01 and size > 0:
                    # This might be a losing position from resolved market
                    # Or a position we already redeemed
                    results["already_redeemed"] += 1
                    continue
                
                print(f"\n   📊 {market_title}...")
                print(f"      Size: {size:.2f} | Value: ${value:.2f}")
                
                # Check if market is resolved
                if not self.check_if_resolved(condition_id):
                    print(f"      ⏳ Not resolved yet")
                    results["not_resolved"] += 1
                    continue
                
                # Market is resolved - try to redeem
                print(f"      ✅ Market resolved - attempting redemption...")
                
                tx_hash = self.redeem_position(condition_id, token_id)
                
                if tx_hash:
                    results["redeemed"] += 1
                    redeemed_conditions.add(condition_id)
                else:
                    results["errors"] += 1
                    
            except Exception as e:
                print(f"      ❌ Error: {e}")
                results["errors"] += 1
        
        print(f"\n📊 Redemption Summary:")
        print(f"   Scanned: {results['scanned']}")
        print(f"   Redeemed: {results['redeemed']}")
        print(f"   Not Resolved: {results['not_resolved']}")
        print(f"   Already Done: {results['already_redeemed']}")
        print(f"   Errors: {results['errors']}")
        
        return results
    
    def run_loop(self, interval: int = 300):
        """Run redemption loop continuously."""
        print(f"\n🔄 Starting auto-redemption loop (every {interval}s)")
        
        while True:
            try:
                self.scan_and_redeem()
            except Exception as e:
                print(f"Error in redemption loop: {e}")
            
            print(f"\n   ⏳ Next scan in {interval}s...")
            time.sleep(interval)


def redeem_all_positions() -> Dict:
    """One-shot function to redeem all redeemable positions."""
    redeemer = AutoRedeemer()
    return redeemer.scan_and_redeem()


if __name__ == "__main__":
    import sys
    
    if "--loop" in sys.argv:
        redeemer = AutoRedeemer()
        redeemer.run_loop(interval=300)
    else:
        # One-shot redemption
        redeem_all_positions()
