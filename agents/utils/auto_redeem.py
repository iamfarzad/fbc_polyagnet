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

        # Use DASHBOARD_WALLET for positions (same as API) - fallback to proxy for transactions
        self.dashboard_wallet = os.getenv("DASHBOARD_WALLET", "0xdb1f88Ab5B531911326788C018D397d352B7265c")
        self.proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER")

        self.address = None
        if self.private_key:
            self.account = Account.from_key(self.private_key)
            # Use dashboard wallet for position queries, proxy for Gnosis Safe transactions
            self.address = self.dashboard_wallet  # Always use dashboard wallet for positions
            print(f"   🏦 AutoRedeemer using dashboard wallet: {self.address} (Proxy: {self.proxy_address})")
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

        # Failure tracking to prevent loops
        self.failed_attempts = {}


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
        print(f"   📡 REDEEMER: Found {len(positions)} positions from API")
        added = 0
        for i, pos in enumerate(positions[:5]):  # Debug first 5
            # Handle varied API response keys
            cond_id = pos.get("conditionId") or pos.get("condition_id")
            token_id = pos.get("asset") or pos.get("tokenId")
            market_title = pos.get("title", "Unknown")[:40]
            size = float(pos.get("size", 0))

            # Only track if we have shares
            if size <= 0:
                continue

            if i < 3:  # Debug log first 3
                print(f"   📡 Processing position {i+1}: {market_title} (size: {size})")

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

    def get_token_balance(self, token_id: str, account_address: str) -> int:
        """Check on-chain token balance before attempting redemption."""
        try:
            # Convert token_id to int (handles hex strings and decimal strings)
            if isinstance(token_id, str):
                if token_id.startswith("0x"):
                    token_id_int = int(token_id, 16)
                else:
                    token_id_int = int(token_id)
            else:
                token_id_int = int(token_id)
            
            # Check balance on-chain
            balance = self.ctf.functions.balanceOf(
                Web3.to_checksum_address(account_address),
                token_id_int
            ).call()
            return balance
        except Exception as e:
            print(f"   ⚠️ Balance check failed for token {token_id[:20]}...: {e}")
            return 0

    def redeem_settled_positions(self) -> int:
        """Check all positions and redeem any that are already settled."""
        positions = self.get_positions_from_api()
        redeemed = 0

        for pos in positions:
            # Skip if already claimed
            if pos.get("claimed"):
                continue

            cond_id = pos.get("conditionId") or pos.get("condition_id")
            token_id = pos.get("asset") or pos.get("tokenId")
            market_title = pos.get("title", "Unknown")[:40]
            size = float(pos.get("size", 0))

            if not cond_id or size <= 0:
                continue

            # Check if this market is already resolved
            print(f"   🔍 Checking if {market_title[:30]}... is resolved (cond_id: {cond_id[:10]}...)")
            is_resolved = self.check_if_resolved(cond_id)
            print(f"   🔍 Resolution check result: {is_resolved}")
            if is_resolved:
                # CRITICAL FIX: Check on-chain balance before attempting redemption
                # This prevents "execution reverted" when positions were manually redeemed
                # Use proxy_address if available (for Gnosis Safe), otherwise dashboard_wallet
                account_to_check = self.proxy_address if self.proxy_address else self.dashboard_wallet
                if not account_to_check:
                    print(f"   ⚠️ Skipping {market_title[:30]}...: No account address")
                    continue
                
                on_chain_balance = self.get_token_balance(token_id, account_to_check)
                if on_chain_balance <= 0:
                    print(f"   ⚠️ Skipping {market_title[:30]}...: On-chain balance is 0 (already redeemed)")
                    continue
                
                print(f"   🎯 SETTLED POSITION FOUND: {market_title} (Size: {size}, On-chain: {on_chain_balance})")
                tx = self.redeem_position(cond_id, token_id)
                if tx:
                    redeemed += 1
                    print(f"   💰 REDEEMED SETTLED POSITION: {tx}")
                else:
                    print(f"   ❌ FAILED TO REDEEM SETTLED POSITION")

        return redeemed

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
            resolved = any(p > 0 for p in payouts)
            print(f"   🔗 On-chain check for {condition_id[:10]}...: payouts={payouts}, resolved={resolved}")
            return resolved
        except Exception as e:
            print(f"   🔗 On-chain check failed for {condition_id[:10]}...: {e}")
            return False

    def redeem_position(self, condition_id: str, token_id: str) -> Optional[str]:
        if not self.private_key: return None
        
        # STOP ZOMBIE LOOP: Check failures
        if self.failed_attempts.get(condition_id, 0) > 3:
            # print(f"   🛑 Skipping {condition_id[:10]}... (Too many failures)")
            return None
            
        try:
            if not condition_id.startswith("0x"): condition_id = "0x" + condition_id
            condition_bytes = bytes.fromhex(condition_id[2:].zfill(64))

            is_proxy = False
            proxy_address = self.proxy_address
            if proxy_address and self.address.lower() == proxy_address.lower():
                is_proxy = True

            parent_collection = bytes(32)
            index_sets = [1, 2] # Yes and No

            # Encode the action the Safe will perform
            inner_data = self.ctf.encodeABI(
                fn_name="redeemPositions",
                args=[Web3.to_checksum_address(USDC_ADDRESS), parent_collection, condition_bytes, index_sets]
            )

            if is_proxy:
                # 1. Setup Safe Contract with getTransactionHash
                SAFE_ABI_EXTENDED = [
                    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address","name":"refundReceiver","type":"address"},{"internalType":"uint256","name":"nonce","type":"uint256"}],"name":"getTransactionHash","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},
                    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"success","type":"bool"}],"stateMutability":"payable","type":"function"},
                    {"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
                ]
                proxy_contract = self.w3.eth.contract(address=self.address, abi=SAFE_ABI_EXTENDED)

                # 2. Get the Safe's current nonce and official hash
                safe_nonce = proxy_contract.functions.nonce().call()
                to_addr = Web3.to_checksum_address(CONDITIONAL_TOKENS)

                # Use the contract to generate the hash (Foolproof)
                tx_hash_bytes = proxy_contract.functions.getTransactionHash(
                    to_addr, 0, inner_data, 0, 500000, 0, 0,
                    "0x0000000000000000000000000000000000000000",
                    "0x0000000000000000000000000000000000000000",
                    safe_nonce
                ).call()

                # 3. Sign the hash
                signed_hash = self.w3.eth.account._sign_hash(tx_hash_bytes, private_key=self.private_key)
                signature = signed_hash.r.to_bytes(32, 'big') + signed_hash.s.to_bytes(32, 'big') + signed_hash.v.to_bytes(1, 'big')

                # 4. Execute Outer Tx (CRITICAL: gas > 500,000)
                tx = proxy_contract.functions.execTransaction(
                    to_addr, 0, inner_data, 0, 500000, 0, 0,
                    "0x0000000000000000000000000000000000000000",
                    "0x0000000000000000000000000000000000000000",
                    signature
                ).build_transaction({
                    'from': self.account.address,
                    'nonce': self.w3.eth.get_transaction_count(self.account.address),
                    'gas': 650000, # Set to 650k to cover inner 500k + overhead
                    'gasPrice': self.w3.eth.gas_price,
                    'chainId': 137
                })

                signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                print(f"   ✅ Turbo Redemption Sent: {tx_hash.hex()}")
                return tx_hash.hex()

            # Standard EOA logic below... (keep as is)
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
            self.failed_attempts[condition_id] = self.failed_attempts.get(condition_id, 0) + 1
            return None

    def settlement_sniper(self):
        """High-frequency check for markets that just reached their end_time."""
        now = time.time()
        to_redeem = []
        to_remove = []  # Track positions already redeemed to remove from watchlist

        for cond_id, data in list(self.market_watchlist.items()):  # Use list() to avoid modification during iteration
            # If the market duration has passed, check on-chain status IMMEDIATELY
            if now >= data["end_time"]:
                # Only log verbose check once per minute to avoid spamming
                if now % 60 < 10: 
                    print(f"   🎯 TARGET REACHED: {data['title']} (Checking oracle...)")
                    
                if self.check_if_resolved(cond_id):
                    # CRITICAL FIX: Check on-chain balance before attempting redemption
                    # Use proxy_address if available (for Gnosis Safe), otherwise dashboard_wallet
                    account_to_check = self.proxy_address if self.proxy_address else self.dashboard_wallet
                    if account_to_check:
                        token_id = data["token_id"]
                        on_chain_balance = self.get_token_balance(token_id, account_to_check)
                        if on_chain_balance <= 0:
                            print(f"   ⚠️ Skipping {data['title'][:30]}...: On-chain balance is 0 (already redeemed)")
                            # Mark for removal from watchlist since it's already redeemed
                            to_remove.append(cond_id)
                            continue
                    
                    print(f"   🚀 ORACLE CONFIRMED: {data['title']} - SNIPING NOW!")
                    to_redeem.append((cond_id, data["token_id"]))

        # Remove already-redeemed positions from watchlist
        for cond_id in to_remove:
            if cond_id in self.market_watchlist:
                del self.market_watchlist[cond_id]

        # Attempt redemption for positions that need it
        for cond_id, token_id in to_redeem:
            tx = self.redeem_position(cond_id, token_id)
            if tx:
                # Remove from watchlist once successful
                if cond_id in self.market_watchlist:
                    del self.market_watchlist[cond_id]
                self._force_agent_reinvest()

    def _force_agent_reinvest(self):
        """Forces all agents to update their balance via Supabase (Global Signal)."""
        try:
            # 1. Update Global State in Supabase
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                from agents.utils.supabase_client import get_supabase_state
                supa = get_supabase_state()
                if supa:
                    # Update a global 'last_win' timestamp or similar to trigger refresh
                    # For now, we update 'sports_trader' status as a carrier signal, or just log activity
                    supa.update_agent_state("sports_trader", {
                        "last_win_time": datetime.datetime.now().isoformat(),
                         "force_refresh": True
                    })
                    print("   💰 Compounding: GLOBAL SIGNAL SENT via Supabase.")
            except Exception as se:
                print(f"   ⚠️ Supabase signaling failed: {se}")

            # 2. Local Fallback
            from agents.utils.context import get_context
            ctx = get_context()
            print("   💰 Compounding: Local signal sent.")
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

        # NEW: Also check for already settled positions and redeem them immediately
        settled_redeemed = self.redeem_settled_positions()

        # Track what gets redeemed from watchlist
        before_count = len(self.market_watchlist)
        self.settlement_sniper()
        after_count = len(self.market_watchlist)

        watchlist_redeemed = before_count - after_count
        total_redeemed = settled_redeemed + watchlist_redeemed
        return {"redeemed": max(0, total_redeemed)}

def redeem_all_positions() -> Dict:
    """One-shot function (standard mode)"""
    redeemer = AutoRedeemer()
    redeemer.run_turbo_loop() # Default to turbo for this call for now
    return {}

if __name__ == "__main__":
    redeemer = AutoRedeemer()
    redeemer.run_turbo_loop()
