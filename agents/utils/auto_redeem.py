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

        # CRITICAL FIX: For Gnosis Safe operations, self.address MUST be the proxy
        # The proxy holds the tokens, not the EOA signer
        self.proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER")

        self.address = None
        if self.private_key:
            self.account = Account.from_key(self.private_key)
            # PRIORITIZE PROXY ADDRESS for Gnosis Safe operations
            self.address = self.proxy_address if self.proxy_address else self.account.address
            print(f"   🏦 AutoRedeemer using address: {self.address} (Proxy: {self.proxy_address is not None})")
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
        """Redeem a winning position. Supports both EOA and Gnosis Safe Proxy."""
        if not self.private_key:
            return None
        
        try:
            # Prepare condition_id as bytes32
            if not condition_id.startswith("0x"):
                condition_id = "0x" + condition_id
            condition_bytes = bytes.fromhex(condition_id[2:].zfill(64))
            
            # Check if using Proxy
            is_proxy = False
            proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER")
            # If our configured address matches the proxy environment variable, we are in Proxy Mode
            if proxy_address and self.address.lower() == proxy_address.lower():
                is_proxy = True
                print(f"   🛡️ Detected Proxy Mode: {proxy_address}")

            # Parent collection and index sets
            parent_collection = bytes(32)
            index_sets = [1, 2] # Binary markets
            
            # ---------------------------------------------------------
            # PATH A: GNOSIS SAFE PROXY REDEMPTION
            # ---------------------------------------------------------
            if is_proxy:
                # 1. Encode Inner Call (CTF.redeemPositions)
                inner_data = self.ctf.encodeABI(
                    fn_name="redeemPositions",
                    args=[
                        Web3.to_checksum_address(USDC_ADDRESS),
                        parent_collection,
                        condition_bytes,
                        index_sets
                    ]
                )
                
                # 2. Setup Proxy Contract
                # Minimal Safe ABI for execTransaction and nonce
                SAFE_ABI_MIN = [
                    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"success","type":"bool"}],"stateMutability":"payable","type":"function"},
                    {"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
                ]
                proxy_contract = self.w3.eth.contract(address=self.address, abi=SAFE_ABI_MIN)
                
                # 3. Get Safe Nonce
                safe_nonce = proxy_contract.functions.nonce().call()
                
                # 4. Helper to calculate Safe Hash (EIP-712)
                def get_safe_tx_hash(safe_address, to, value, data, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce, chain_id):
                    DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
                    domain_separator = Web3.solidity_keccak(['bytes32', 'uint256', 'address'], [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe_address])
                    SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")
                    data_hash = Web3.keccak(hexstr=data)
                    safe_tx_hash = Web3.solidity_keccak(['bytes32', 'address', 'uint256', 'bytes32', 'uint8', 'uint256', 'uint256', 'uint256', 'address', 'address', 'uint256'], [SAFE_TX_TYPEHASH, to, value, data_hash, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce])
                    return Web3.solidity_keccak(['bytes1', 'bytes1', 'bytes32', 'bytes32'], [bytes.fromhex('19'), bytes.fromhex('01'), domain_separator, safe_tx_hash])

                # 5. Build Safe Transaction Params
                to_addr = Web3.to_checksum_address(CONDITIONAL_TOKENS)
                value = 0
                operation = 0 # Call
                safe_tx_gas = 500000
                base_gas = 0
                gas_price = 0
                gas_token = "0x0000000000000000000000000000000000000000"
                refund_receiver = "0x0000000000000000000000000000000000000000"
                chain_id = 137
                
                # 6. Sign Hash
                tx_hash_bytes = get_safe_tx_hash(self.address, to_addr, value, inner_data, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, safe_nonce, chain_id)
                signed_hash = self.w3.eth.account._sign_hash(tx_hash_bytes, private_key=self.private_key)
                
                # Pack Signature (r + s + v)
                signature = signed_hash.r.to_bytes(32, 'big') + signed_hash.s.to_bytes(32, 'big') + signed_hash.v.to_bytes(1, 'big')

                # 7. Execute Outer Transaction (Meta-Transaction)
                # Note: 'from' must be the EOA (private key holder), calling 'execTransaction' on the Proxy
                tx = proxy_contract.functions.execTransaction(
                    to_addr, value, inner_data, operation, 
                    safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, 
                    signature
                ).build_transaction({
                    'from': self.account.address, # Use EOA address here
                    'nonce': self.w3.eth.get_transaction_count(self.account.address),
                    'gas': 400000,
                    'gasPrice': self.w3.eth.gas_price,
                    'chainId': 137
                })
                
                signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                print(f"   ✅ Proxy Redemption Sent: {tx_hash.hex()}")
                return tx_hash.hex()

            # ---------------------------------------------------------
            # PATH B: STANDARD EOA REDEMPTION
            # ---------------------------------------------------------
            else:
                # Build transaction directly on CTF
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
