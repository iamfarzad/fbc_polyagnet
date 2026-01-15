"""
PROXY WITHDRAWAL SCRIPT (GNOSIS SAFE)
Withdraws all USDC from the Proxy Safe back to the Main Wallet (Owner).

Target Proxy: 0xdb1f88Ab5B531911326788C018D397d352B7265c
Receiver (Owner): 0x3C5179f63E580c890950ac7dfCf96e750fB2D046

Usage:
    python agents/scripts/python/withdraw_from_proxy.py
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

# --- CONFIGURATION ---
PROXY_ADDRESS = "0xdb1f88Ab5B531911326788C018D397d352B7265c"
OWNER_ADDRESS = "0x3C5179f63E580c890950ac7dfCf96e750fB2D046"
POLYGON_RPC = os.getenv("POLYGON_RPC", "https://polygon-bor.publicnode.com")
PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")

# --- CONTRACTS ---
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# --- ABIS ---
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

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

def get_safe_tx_hash(safe_address, to, value, data, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce, chain_id):
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

def main():
    print(f"="*60)
    print(f"💸 PROXY WITHDRAWAL (Safe -> Main)")
    print(f"="*60)

    if not PRIVATE_KEY:
        print("❌ Error: Missing POLYGON_WALLET_PRIVATE_KEY in .env")
        return

    w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
    account = Account.from_key(PRIVATE_KEY)
    
    proxy_contract = w3.eth.contract(address=PROXY_ADDRESS, abi=SAFE_ABI)
    usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
    
    print(f"   Signer (Owner): {account.address}")
    print(f"   Target (Proxy): {PROXY_ADDRESS}")
    print(f"   Receiver:       {OWNER_ADDRESS}")

    # 1. Check Balance
    print("\n💰 Checking Proxy Balance...")
    balance = usdc_contract.functions.balanceOf(PROXY_ADDRESS).call()
    
    if balance == 0:
        print("   ❌ Balance is 0. Nothing to withdraw.")
        return

    human_balance = balance / 10**6
    print(f"   ✅ Balance Found: ${human_balance:,.2f} USDC")

    # 2. Build Inner Transaction (USDC Transfer)
    print("\n📦 Building Withdrawal Transaction...")
    inner_data = usdc_contract.encodeABI(
        fn_name="transfer",
        args=[
            Web3.to_checksum_address(OWNER_ADDRESS),
            balance
        ]
    )

    # 3. Build & Sign Safe Transaction
    to = Web3.to_checksum_address(USDC_ADDRESS)
    value = 0
    operation = 0 # Call
    safe_tx_gas = 200000
    base_gas = 0
    gas_price = 0
    gas_token = "0x0000000000000000000000000000000000000000"
    refund_receiver = "0x0000000000000000000000000000000000000000"
    chain_id = 137
    
    try:
        nonce = proxy_contract.functions.nonce().call()
    except Exception as e:
        print(f"   ❌ Error fetching nonce: {e}")
        return

    tx_hash_bytes = get_safe_tx_hash(
        PROXY_ADDRESS, to, value, inner_data, operation, 
        safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, 
        nonce, chain_id
    )

    signed = w3.eth.account._sign_hash(tx_hash_bytes, private_key=PRIVATE_KEY)
    r_bytes = signed.r.to_bytes(32, 'big')
    s_bytes = signed.s.to_bytes(32, 'big')
    v_bytes = signed.v.to_bytes(1, 'big')
    signature = r_bytes + s_bytes + v_bytes

    # 4. Execute
    print("   📝 Signing & Sending...")
    try:
        tx = proxy_contract.functions.execTransaction(
            to, value, inner_data, operation, 
            safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, 
            signature
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 200000,
            'gasPrice': w3.eth.gas_price,
            'chainId': 137
        })
        
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        print(f"   ✅ Sent! TX: https://polygonscan.com/tx/{tx_hash.hex()}")
        print("   ⏳ Waiting for confirmation...")
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        print("   🎉 Confirmed! Funds moved to Main Wallet.")
        
    except Exception as e:
        print(f"   ❌ Withdrawal Failed: {e}")

if __name__ == "__main__":
    main()
