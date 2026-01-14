"""
Wallet Consolidation Script

Transfers all open positions (ERC-1155) and liquid USDC.e (ERC-20) from the
original Trust Wallet (EOA) to the new Proxy Vault.

Prerequisites:
- pip install web3 requests python-dotenv
- Ensure Trust Wallet has at least 0.5-1.0 MATIC for gas fees

Usage:
    python consolidate_wallets.py
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

try:
    from web3 import Web3
except ImportError:
    print("❌ web3 not installed. Run: pip install web3")
    sys.exit(1)

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

RPC_URL = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Wallet Addresses
EOA_ADDRESS = "0x3C5179f63E580c890950ac7dfCf96e750fB2D046"
PROXY_ADDRESS = "0xdb1f88Ab5B531911326788C018D397d352B7265c"

# Private key from environment (NEVER hardcode this)
PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")

# Contract Addresses on Polygon
# CTF Token Contract (ERC-1155) - NOT the CTF Exchange
CTF_ADDRESS = Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")
USDC_E_ADDRESS = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")

# ABIs (minimal)
CTF_ABI = json.loads('''[
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256[]", "name": "ids", "type": "uint256[]"},
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"},
            {"internalType": "bytes", "name": "data", "type": "bytes"}
        ],
        "name": "safeBatchTransferFrom",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "account", "type": "address"},
            {"internalType": "uint256", "name": "id", "type": "uint256"}
        ],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]''')

ERC20_ABI = json.loads('''[
    {
        "constant": false,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]''')


def check_prerequisites():
    """Verify we have everything needed before proceeding."""
    print("\n🔍 Checking prerequisites...")
    
    if not PRIVATE_KEY:
        print("❌ POLYGON_WALLET_PRIVATE_KEY not set in environment.")
        print("   Set it in your .env file or export it.")
        return False
    
    if not w3.is_connected():
        print("❌ Cannot connect to Polygon RPC.")
        return False
    
    # Check MATIC balance for gas
    matic_balance = w3.eth.get_balance(EOA_ADDRESS)
    matic_balance_eth = w3.from_wei(matic_balance, 'ether')
    
    print(f"✅ Connected to Polygon")
    print(f"💎 MATIC Balance: {matic_balance_eth:.4f}")
    
    if matic_balance_eth < 0.1:
        print("⚠️  Warning: Low MATIC balance. You may need more for gas fees.")
    
    return True


def fetch_open_positions():
    """Fetch all open positions from the Data API."""
    print(f"\n📡 Scanning {EOA_ADDRESS[:10]}... for open positions...")
    
    url = f"https://data-api.polymarket.com/positions?user={EOA_ADDRESS}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        positions = response.json()
        
        valid_positions = []
        for pos in positions:
            size = float(pos.get('size', 0) or 0)
            if size > 0:
                valid_positions.append({
                    'title': pos.get('title', 'Unknown'),
                    'asset_id': pos.get('asset'),
                    'size': size,
                    'current_value': float(pos.get('currentValue', 0) or 0)
                })
        
        return valid_positions
    except Exception as e:
        print(f"❌ Error fetching positions: {e}")
        return []


def transfer_erc1155_positions(positions):
    """
    Transfer all ERC-1155 outcome tokens in a single batch transaction.
    """
    if not positions:
        print("ℹ️  No ERC-1155 positions to transfer.")
        return None
    
    print(f"\n🚀 Preparing batch transfer of {len(positions)} positions...")
    
    ctf_contract = w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
    
    token_ids = []
    amounts = []
    
    for pos in positions:
        try:
            # Asset ID is the token ID
            token_id = int(pos['asset_id'])
            
            # Get actual on-chain balance (more accurate than API)
            on_chain_balance = ctf_contract.functions.balanceOf(
                Web3.to_checksum_address(EOA_ADDRESS),
                token_id
            ).call()
            
            if on_chain_balance > 0:
                token_ids.append(token_id)
                amounts.append(on_chain_balance)
                print(f"  ✅ {pos['title'][:50]}...")
                print(f"     Token ID: {token_id}")
                print(f"     Amount: {on_chain_balance}")
        except Exception as e:
            print(f"  ⚠️  Error processing {pos['title'][:30]}: {e}")
            continue
    
    if not token_ids:
        print("ℹ️  No valid positions found on-chain to transfer.")
        return None
    
    # Build transaction with boosted gas price for faster confirmation
    nonce = w3.eth.get_transaction_count(EOA_ADDRESS)
    base_gas_price = w3.eth.gas_price
    boosted_gas_price = int(base_gas_price * 1.5)  # 50% boost for priority
    print(f"\n⛽ Gas Price: {w3.from_wei(boosted_gas_price, 'gwei'):.2f} Gwei (1.5x boost)")
    
    print(f"\n📦 Building batch transfer transaction...")
    print(f"   From: {EOA_ADDRESS}")
    print(f"   To: {PROXY_ADDRESS}")
    print(f"   Positions: {len(token_ids)}")
    
    try:
        txn = ctf_contract.functions.safeBatchTransferFrom(
            Web3.to_checksum_address(EOA_ADDRESS),
            Web3.to_checksum_address(PROXY_ADDRESS),
            token_ids,
            amounts,
            b''
        ).build_transaction({
            'chainId': 137,
            'gas': 50000 + (len(token_ids) * 50000),  # Dynamic gas based on position count
            'gasPrice': boosted_gas_price,
            'nonce': nonce,
        })
        
        signed_txn = w3.eth.account.sign_transaction(txn, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        print(f"\n🎉 ERC-1155 Batch Transfer Sent!")
        print(f"   TX Hash: {w3.to_hex(tx_hash)}")
        print(f"   View: https://polygonscan.com/tx/{w3.to_hex(tx_hash)}")
        
        return tx_hash
        
    except Exception as e:
        print(f"\n❌ Transaction failed: {e}")
        return None


def transfer_usdc():
    """
    Transfer all USDC.e balance to the Proxy wallet.
    """
    print(f"\n💰 Checking USDC.e balance...")
    
    usdc_contract = w3.eth.contract(address=USDC_E_ADDRESS, abi=ERC20_ABI)
    raw_balance = usdc_contract.functions.balanceOf(EOA_ADDRESS).call()
    
    if raw_balance == 0:
        print("ℹ️  No USDC.e balance to transfer.")
        return None
    
    usdc_amount = raw_balance / 10**6  # USDC has 6 decimals
    print(f"   Balance: ${usdc_amount:,.2f}")
    
    nonce = w3.eth.get_transaction_count(EOA_ADDRESS)
    base_gas_price = w3.eth.gas_price
    boosted_gas_price = int(base_gas_price * 1.5)
    
    print(f"\n📦 Building USDC.e transfer...")
    
    try:
        txn = usdc_contract.functions.transfer(
            Web3.to_checksum_address(PROXY_ADDRESS),
            raw_balance
        ).build_transaction({
            'chainId': 137,
            'gas': 100000,
            'gasPrice': boosted_gas_price,
            'nonce': nonce,
        })
        
        signed_txn = w3.eth.account.sign_transaction(txn, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        print(f"\n🎉 USDC.e Transfer Sent!")
        print(f"   TX Hash: {w3.to_hex(tx_hash)}")
        print(f"   View: https://polygonscan.com/tx/{w3.to_hex(tx_hash)}")
        
        return tx_hash
        
    except Exception as e:
        print(f"\n❌ USDC transfer failed: {e}")
        return None


def main():
    print("\n" + "="*60)
    print("  🔄 WALLET CONSOLIDATION SCRIPT")
    print("="*60)
    print(f"\n  From: {EOA_ADDRESS}")
    print(f"  To:   {PROXY_ADDRESS}")
    print("="*60)
    
    if not check_prerequisites():
        sys.exit(1)
    
    # Confirmation prompt
    print("\n⚠️  This will transfer ALL positions and USDC.e to the Proxy wallet.")
    confirm = input("   Type 'YES' to continue: ")
    
    if confirm.strip().upper() != 'YES':
        print("\n❌ Aborted.")
        sys.exit(0)
    
    # Phase 1: Transfer ERC-1155 positions
    positions = fetch_open_positions()
    if positions:
        print(f"\n📋 Found {len(positions)} open positions:")
        for i, pos in enumerate(positions, 1):
            print(f"   {i}. {pos['title'][:50]}... (${pos['current_value']:.2f})")
        
        erc1155_tx = transfer_erc1155_positions(positions)
        
        if erc1155_tx:
            print("\n⏳ Waiting for ERC-1155 transaction to be mined...")
            receipt = w3.eth.wait_for_transaction_receipt(erc1155_tx, timeout=120)
            if receipt['status'] == 1:
                print("✅ ERC-1155 transfer confirmed!")
            else:
                print("❌ ERC-1155 transfer failed on-chain.")
    
    # Phase 2: Transfer USDC.e
    usdc_tx = transfer_usdc()
    
    if usdc_tx:
        print("\n⏳ Waiting for USDC.e transaction to be mined...")
        receipt = w3.eth.wait_for_transaction_receipt(usdc_tx, timeout=120)
        if receipt['status'] == 1:
            print("✅ USDC.e transfer confirmed!")
        else:
            print("❌ USDC.e transfer failed on-chain.")
    
    print("\n" + "="*60)
    print("  ✅ CONSOLIDATION COMPLETE")
    print("="*60)
    print(f"\n  Your positions and funds are now in: {PROXY_ADDRESS}")
    print("  Refresh Polymarket to see your updated portfolio.")
    print("\n")


if __name__ == "__main__":
    main()
