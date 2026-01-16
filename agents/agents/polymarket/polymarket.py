# core polymarket api
# https://github.com/Polymarket/py-clob-client/tree/main/examples

import os
import pdb
import time
import ast
import json
import base64
import requests
import websocket
import threading
from typing import Dict, List, Optional, Callable

from dotenv import load_dotenv

from web3 import Web3
from web3.constants import MAX_INT
from web3.middleware import geth_poa_middleware

import httpx
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import AMOY, POLYGON
from py_order_utils.builders import OrderBuilder
from py_order_utils.model import OrderData
from py_order_utils.signer import Signer
from py_clob_client.clob_types import (
    OrderArgs,
    MarketOrderArgs,
    OrderType,
    OrderBookSummary,
)
from py_clob_client.order_builder.constants import BUY

from agents.utils.objects import SimpleMarket, SimpleEvent

load_dotenv()


class Polymarket:
    def __init__(self) -> None:
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.gamma_markets_endpoint = self.gamma_url + "/markets"
        self.gamma_events_endpoint = self.gamma_url + "/events"

        self.clob_url = "https://clob.polymarket.com"
        self.clob_auth_endpoint = self.clob_url + "/auth/api-key"

        self.chain_id = 137  # POLYGON

        # --- KEY FIX START ---
        # Fetch key, strip whitespace/newlines, remove quotes
        pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY", "").strip().replace('"', '').replace("'", "")
        # Ensure '0x' prefix is present (standardizes Hex format)
        if pk and not pk.startswith("0x"):
            pk = "0x" + pk
        self.private_key = pk
        # --- KEY FIX END ---

        self.polygon_rpc = "https://polygon-rpc.com"
        self.w3 = Web3(Web3.HTTPProvider(self.polygon_rpc))

        self.exchange_address = Web3.to_checksum_address("0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e")
        self.neg_risk_exchange_address = Web3.to_checksum_address("0xC5d563A36AE78145C45a50134d48A1215220f80a")

        self.erc20_approve = """[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"owner","type":"address"},{"indexed":true,"internalType":"address","name":"spender","type":"address"},{"indexed":false,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"authorizer","type":"address"},{"indexed":true,"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"AuthorizationCanceled","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"authorizer","type":"address"},{"indexed":true,"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"AuthorizationUsed","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"account","type":"address"}],"name":"Blacklisted","type":"event"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"address","name":"userAddress","type":"address"},{"indexed":false,"internalType":"address payable","name":"relayerAddress","type":"address"},{"indexed":false,"internalType":"bytes","name":"functionSignature","type":"bytes"}],"name":"MetaTransactionExecuted","type":"event"},{"anonymous":false,"inputs":[],"name":"Pause","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"newRescuer","type":"address"}],"name":"RescuerChanged","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"bytes32","name":"previousAdminRole","type":"bytes32"},{"indexed":true,"internalType":"bytes32","name":"newAdminRole","type":"bytes32"}],"name":"RoleAdminChanged","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleGranted","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleRevoked","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"from","type":"address"},{"indexed":true,"internalType":"address","name":"to","type":"address"},{"indexed":false,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"account","type":"address"}],"name":"UnBlacklisted","type":"event"},{"anonymous":false,"inputs":[],"name":"Unpause","type":"event"},{"inputs":[],"name":"APPROVE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"BLACKLISTER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"CANCEL_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DECREASE_ALLOWANCE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DEFAULT_ADMIN_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DEPOSITOR_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DOMAIN_SEPARATOR","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"EIP712_VERSION","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"INCREASE_ALLOWANCE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"META_TRANSACTION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"PAUSER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"PERMIT_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"RESCUER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"TRANSFER_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"WITHDRAW_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"approveWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"authorizer","type":"address"},{"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"authorizationState","outputs":[{"internalType":"enum GasAbstraction.AuthorizationState","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"blacklist","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"blacklisters","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"authorizer","type":"address"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"cancelAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"subtractedValue","type":"uint256"}],"name":"decreaseAllowance","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"decrement","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"decreaseAllowanceWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"user","type":"address"},{"internalType":"bytes","name":"depositData","type":"bytes"}],"name":"deposit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"userAddress","type":"address"},{"internalType":"bytes","name":"functionSignature","type":"bytes"},{"internalType":"bytes32","name":"sigR","type":"bytes32"},{"internalType":"bytes32","name":"sigS","type":"bytes32"},{"internalType":"uint8","name":"sigV","type":"uint8"}],"name":"executeMetaTransaction","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleAdmin","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"uint256","name":"index","type":"uint256"}],"name":"getRoleMember","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleMemberCount","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"grantRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"hasRole","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"addedValue","type":"uint256"}],"name":"increaseAllowance","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"increment","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"increaseAllowanceWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"newName","type":"string"},{"internalType":"string","name":"newSymbol","type":"string"},{"internalType":"uint8","name":"newDecimals","type":"uint8"},{"internalType":"address","name":"childChainManager","type":"address"}],"name":"initialize","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"initialized","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"isBlacklisted","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"}],"name":"nonces","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pause","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"paused","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pausers","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"permit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"renounceRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"tokenContract","type":"address"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"rescueERC20","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"rescuers","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"revokeRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"sender","type":"address"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transferFrom","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"from","type":"address"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"transferWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"unBlacklist","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"unpause","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"newName","type":"string"},{"internalType":"string","name":"newSymbol","type":"string"}],"name":"updateMetadata","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"withdrawWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"}]"""
        self.erc1155_set_approval = """[{"inputs": [{ "internalType": "address", "name": "operator", "type": "address" },{ "internalType": "bool", "name": "approved", "type": "bool" }],"name": "setApprovalForAll","outputs": [],"stateMutability": "nonpayable","type": "function"}]"""

        self.usdc_address = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
        self.ctf_address = Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")

        self.web3 = Web3(Web3.HTTPProvider(self.polygon_rpc))
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.usdc = self.web3.eth.contract(
            address=self.usdc_address, abi=self.erc20_approve
        )
        self.ctf = self.web3.eth.contract(
            address=self.ctf_address, abi=self.erc1155_set_approval
        )

        # Ensure funder_address is always set
        self.funder_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER") or "0xdb1f88Ab5B531911326788C018D397d352B7265c"

        self._init_api_keys()
        self._init_approvals(False)

        # Websocket setup - isolated from main API client
        self.ws_url = "wss://ws-subscriptions-clob.polymarket.com"
        self.ws_connection = None
        self.ws_channel_type = None
        self.ws_auth_token = None
        self.subscribed_markets = set()
        self.subscribed_assets = set()
        self.ws_callbacks = {
            'user': [],
            'market': []
        }
        self.ws_thread = None

    def _init_api_keys(self) -> None:
        # Determine signature type and funder for proper L2 authentication
        # FIX 2: Explicit type conversion to integer (critical for Gnosis Safe)
        signature_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "2"))  # Default to GNOSIS_SAFE
        self.funder_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER")

        if self.funder_address:
            print(f"   🔐 Using signature_type={signature_type}, funder={self.funder_address[:10]}...")
        else:
            print("   ⚠️ No funder address set - derived credentials may not work for trading")

        self.client = ClobClient(
            self.clob_url,
            key=self.private_key,
            chain_id=self.chain_id,
            signature_type=signature_type,
            funder=self.funder_address
        )

        # Check for pre-derived User API credentials (CLOB_* env vars)
        user_api_key = os.getenv("CLOB_API_KEY")
        user_secret = os.getenv("CLOB_SECRET")
        user_passphrase = os.getenv("CLOB_PASS_PHRASE")

        if user_api_key and user_secret and user_passphrase:
            try:
                print("   🔑 Using User API Credentials from .env")
                from py_clob_client.clob_types import ApiCreds

                self.credentials = ApiCreds(
                    api_key=user_api_key,
                    api_secret=user_secret,  # Raw string, no base64 decoding
                    api_passphrase=user_passphrase  # Raw string, no base64 decoding
                )

                print("   ✅ User credentials loaded successfully")
            except Exception as e:
                print(f"   ⚠️ User credentials failed: {e}")
                import traceback
                traceback.print_exc()
                print("   🔐 Falling back to derived credentials...")
                self.credentials = self.client.create_or_derive_api_creds()
        else:
            print("   🔐 No User credentials found, deriving from private key...")
            self.credentials = self.client.create_or_derive_api_creds()


        # Ensure funder_address is set even for derived credentials
        if not hasattr(self, 'funder_address') or not self.funder_address:
            self.funder_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER")

        self.client.set_api_creds(self.credentials)

    def get_usdc_allowance(self) -> float:
        """Check USDC allowance for both exchange and CTF contract"""
        try:
            # For MetaMask users, check allowance from proxy wallet (funder), not EOA
            allowance_address = self.funder_address or self.get_address_for_private_key()

            # Check allowance for CTF Exchange
            exchange_allowance = self.usdc.functions.allowance(allowance_address, self.exchange_address).call()

            # Check allowance for CTF contract
            ctf_allowance = self.usdc.functions.allowance(allowance_address, Web3.to_checksum_address("0x4d97dcd97ec945f40cf65f87097ace5ea0476045")).call()

            # Return the minimum of both allowances
            min_allowance = min(exchange_allowance, ctf_allowance)
            allowance_usd = float(min_allowance) / 10**6

            print(f"Exchange allowance: ${float(exchange_allowance) / 10**6:.2f}")
            print(f"CTF allowance: ${float(ctf_allowance) / 10**6:.2f}")
            print(f"Effective allowance: ${allowance_usd:.2f}")

            return allowance_usd
        except Exception as e:
            print(f"Allowance check failed: {e}")
            return 0.0

    def approve_trading(self) -> None:
        """Approve USDC spending for the exchange (one-time setup)"""
        print("Approving USDC spending...")
        self._init_approvals(run=True)
        print("USDC Approved!")

    def _init_approvals(self, run: bool = False) -> None:
        if not run:
            return

        priv_key = self.private_key
        pub_key = self.get_address_for_private_key()
        chain_id = self.chain_id
        web3 = self.web3
        nonce = web3.eth.get_transaction_count(pub_key)
        usdc = self.usdc
        ctf = self.ctf

        # Approve USDC for CTF Exchange
        raw_usdc_approve_txn = usdc.functions.approve(
            "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print("USDC approved for CTF Exchange:", usdc_approve_tx_receipt)

        # Also approve USDC for CTF contract directly
        nonce = web3.eth.get_transaction_count(pub_key)
        raw_usdc_ctf_txn = usdc.functions.approve(
            Web3.to_checksum_address("0x4d97dcd97ec945f40cf65f87097ace5ea0476045"), int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_ctf_tx = web3.eth.account.sign_transaction(
            raw_usdc_ctf_txn, private_key=priv_key
        )
        send_usdc_ctf_tx = web3.eth.send_raw_transaction(
            signed_usdc_ctf_tx.raw_transaction
        )
        usdc_ctf_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_ctf_tx, 600
        )
        print("USDC approved for CTF contract:", usdc_ctf_tx_receipt)

        # Also approve for the main CTF contract (0x4d97dcd97ec945f40cf65f87097ace5ea0476045)
        nonce = web3.eth.get_transaction_count(pub_key)
        ctf_contract_address = Web3.to_checksum_address("0x4d97dcd97ec945f40cf65f87097ace5ea0476045")
        raw_usdc_main_ctf_txn = usdc.functions.approve(
            ctf_contract_address, int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_main_ctf_tx = web3.eth.account.sign_transaction(
            raw_usdc_main_ctf_txn, private_key=priv_key
        )
        send_usdc_main_ctf_tx = web3.eth.send_raw_transaction(
            signed_usdc_main_ctf_tx.raw_transaction
        )
        usdc_main_ctf_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_main_ctf_tx, 600
        )
        print("USDC approved for main CTF contract:", usdc_main_ctf_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        # Neg Risk CTF Exchange
        raw_usdc_approve_txn = usdc.functions.approve(
            "0xC5d563A36AE78145C45a50134d48A1215220f80a", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0xC5d563A36AE78145C45a50134d48A1215220f80a", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        # Neg Risk Adapter
        raw_usdc_approve_txn = usdc.functions.approve(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

    def get_all_markets(self, limit=100, **kwargs) -> "list[SimpleMarket]":
        markets = []
        params = {"limit": limit}
        params.update(kwargs)
        res = httpx.get(self.gamma_markets_endpoint, params=params)
        if res.status_code == 200:
            for market in res.json():
                try:
                    market_data = self.map_api_to_market(market)
                    markets.append(SimpleMarket(**market_data))
                except Exception as e:
                    print(e)
                    pass
        return markets

    def filter_markets_for_trading(self, markets: "list[SimpleMarket]"):
        tradeable_markets = []
        for market in markets:
            if market.active:
                tradeable_markets.append(market)
        return tradeable_markets

    def get_market(self, token_id: str) -> SimpleMarket:
        params = {"clob_token_ids": token_id}
        res = httpx.get(self.gamma_markets_endpoint, params=params)
        if res.status_code == 200:
            data = res.json()
            market = data[0]
            return self.map_api_to_market(market, token_id)

    def map_api_to_market(self, market, token_id: str = "") -> SimpleMarket:
        market_data = {
            "id": int(market["id"]),
            "question": market["question"],
            "end": market["endDate"],
            "description": market.get("description", ""),
            "active": market["active"],
            # "deployed": market["deployed"],
            "funded": market.get("funded", False),
            "rewardsMinSize": float(market.get("rewardsMinSize", 0) or 0),
            "rewardsMaxSpread": float(market.get("rewardsMaxSpread", 0) or 0),
            "volume": float(market.get("volume", 0) or 0),
            "liquidity": float(market.get("liquidity", 0) or 0),
            "spread": float(market.get("spread", 0) or 0),
            "outcomes": str(market.get("outcomes", "[]")),
            "outcome_prices": str(market.get("outcomePrices", "[]") or "[]"),
            "clob_token_ids": str(market.get("clobTokenIds", "[]")),
            # Add trading fields for crypto scalper
            "best_bid": float(market["bestBid"]) if market.get("bestBid") else None,
            "best_ask": float(market["bestAsk"]) if market.get("bestAsk") else None,
            "accepting_orders": market.get("acceptingOrders", False),
        }
        if token_id:
            market_data["clob_token_ids"] = token_id
        return market_data

    def get_all_events(self) -> "list[SimpleEvent]":
        events = []
        res = httpx.get(self.gamma_events_endpoint)
        if res.status_code == 200:
            print(len(res.json()))
            for event in res.json():
                try:
                    print(1)
                    event_data = self.map_api_to_event(event)
                    events.append(SimpleEvent(**event_data))
                except Exception as e:
                    print(e)
                    pass
        return events

    def map_api_to_event(self, event) -> SimpleEvent:
        description = event["description"] if "description" in event.keys() else ""
        return {
            "id": int(event["id"]),
            "ticker": event["ticker"],
            "slug": event["slug"],
            "title": event["title"],
            "description": description,
            "active": event["active"],
            "closed": event["closed"],
            "archived": event["archived"],
            "new": event["new"],
            "featured": event["featured"],
            "restricted": event["restricted"],
            "end": event["endDate"],
            "markets": ",".join([x["id"] for x in event["markets"]]),
        }

    def filter_events_for_trading(
        self, events: "list[SimpleEvent]"
    ) -> "list[SimpleEvent]":
        tradeable_events = []
        for event in events:
            if (
                event.active
                and not event.restricted
                and not event.archived
                and not event.closed
            ):
                tradeable_events.append(event)
        return tradeable_events

    def get_all_tradeable_events(self) -> "list[SimpleEvent]":
        all_events = self.get_all_events()
        return self.filter_events_for_trading(all_events)

    def get_sampling_simplified_markets(self) -> "list[SimpleEvent]":
        markets = []
        raw_sampling_simplified_markets = self.client.get_sampling_simplified_markets()
        for raw_market in raw_sampling_simplified_markets["data"]:
            token_one_id = raw_market["tokens"][0]["token_id"]
            market = self.get_market(token_one_id)
            markets.append(market)
        return markets

    def get_orderbook(self, token_id: str) -> OrderBookSummary:
        return self.client.get_order_book(token_id)

    def get_orderbook_price(self, token_id: str) -> float:
        return float(self.client.get_price(token_id))

    def get_address_for_private_key(self):
        account = self.w3.eth.account.from_key(str(self.private_key))
        return account.address

    def build_order(
        self,
        market_token: str,
        amount: float,
        nonce: str = str(round(time.time())),  # for cancellations
        side: str = "BUY",
        expiration: str = "0",  # timestamp after which order expires
    ):
        signer = Signer(self.private_key)
        builder = OrderBuilder(self.exchange_address, self.chain_id, signer)

        buy = side == "BUY"
        side = 0 if buy else 1
        maker_amount = amount if buy else 0
        taker_amount = amount if not buy else 0
        order_data = OrderData(
            maker=self.funder_address or self.get_address_for_private_key(),
            tokenId=market_token,
            makerAmount=maker_amount,
            takerAmount=taker_amount,
            feeRateBps="1",
            nonce=nonce,
            side=side,
            expiration=expiration,
        )
        order = builder.build_signed_order(order_data)
        return order

    def execute_order(self, price, size, side, token_id) -> str:
        return self.client.create_and_post_order(
            OrderArgs(price=price, size=size, side=side, token_id=token_id)
        )

    def place_limit_order(self, token_id: str, price: float, size: float, side: str = "BUY", fee_rate_bps: int = 0) -> Dict:
        """
        Place a LIMIT order (Maker).
        Target specific price to capture spread/value.

        FIXED: Strip all formatting, ensure raw float objects, explicit integer fee_rate_bps
        """
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY, SELL

            order_side = BUY if side.upper() == "BUY" else SELL

            # FIX 1: Ensure price and size are raw float objects (no string formatting)
            # FIX 4: Ensure fee_rate_bps is explicitly an integer (mandatory for 15-minute markets)
            clean_price = float(price)  # Strip any formatting
            clean_size = float(size)   # Strip any formatting
            clean_fee_rate_bps = int(fee_rate_bps)  # Must be integer for hash

            # Create and post the limit order
            # Note: py-clob-client defaults to 'GTC' (Good Till Cancel) limit orders
            resp = self.client.create_and_post_order(
                OrderArgs(
                    price=clean_price,
                    size=clean_size,
                    side=order_side,
                    token_id=token_id,
                    fee_rate_bps=clean_fee_rate_bps
                )
            )
            print(f"   🎯 Limit Order Placed: {side} {clean_size} @ {clean_price} | Fee: {clean_fee_rate_bps} bps | Resp: {resp}")
            return resp
        except Exception as e:
            print(f"   ⚠️ Limit Order Failed: {e}")
            return {"error": str(e)}

    def execute_market_order(self, market, amount) -> str:
        token_id = ast.literal_eval(market[0].dict()["metadata"]["clob_token_ids"])[1]
        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=amount,
        )
        signed_order = self.client.create_market_order(order_args)
        print("Execute market order... signed_order ", signed_order)
        resp = self.client.post_order(signed_order, orderType=OrderType.FOK)
        print(resp)
        print("Done!")
        return resp

    def get_usdc_balance(self) -> float:
        # Use POLYMARKET_FUNDER or POLYMARKET_PROXY_ADDRESS (Proxy wallet) if set
        funder_address = os.getenv("POLYMARKET_FUNDER") or os.getenv("POLYMARKET_PROXY_ADDRESS")
        if funder_address:
            balance_address = Web3.to_checksum_address(funder_address)
        else:
            balance_address = self.get_address_for_private_key()

        balance_res = self.usdc.functions.balanceOf(balance_address).call()
        return float(balance_res / 10e5)

    # ============================================================================
    # WEBSOCKET METHODS - Real-time data feeds (Fixed for trade compatibility)
    # ============================================================================

    def _get_ws_auth_token(self) -> str:
        """Get authentication token for websocket connection."""
        if not self.ws_auth_token:
            # Use existing API credentials
            self.ws_auth_token = self.credentials.api_key
        return self.ws_auth_token

    def connect_websocket(self, channel_type: str = "market", markets: List[str] = None, assets: List[str] = None) -> bool:
        """
        Connect to Polymarket websocket for real-time updates.
        Fixed to avoid conflicts with trade execution.

        Args:
            channel_type: "user" or "market"
            markets: List of market IDs (condition IDs) for user channel
            assets: List of asset IDs (token IDs) for market channel
        """
        try:
            # Check if already connected to this channel
            if self.ws_connection and self.ws_channel_type == channel_type:
                print(f"WS already connected to {channel_type} channel")
                return True

            auth_token = self._get_ws_auth_token()

            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    # Call registered callbacks
                    for callback in self.ws_callbacks.get(channel_type, []):
                        callback(data)
                except Exception as e:
                    print(f"WS message parse error: {e}")

            def on_error(ws, error):
                print(f"WS error: {error}")

            def on_close(ws, close_status_code, close_msg):
                print(f"WS closed: {close_status_code} - {close_msg}")
                # Reset connection state
                self.ws_connection = None
                self.ws_channel_type = None

            def on_open(ws):
                try:
                    # Send subscription message
                    subscription_msg = {
                        "auth": auth_token,
                        "type": channel_type.upper(),
                        "custom_feature_enabled": False
                    }
                    ws.send(json.dumps(subscription_msg))
                    print(f"WS connected and subscribed to {channel_type} channel")
                    self.ws_channel_type = channel_type
                except Exception as e:
                    print(f"WS subscription error: {e}")

            # Use correct channel URL
            channel_url = f"{self.ws_url}/ws/{channel_type}"

            self.ws_connection = websocket.WebSocketApp(
                channel_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )

            # Start websocket in background thread - NON-BLOCKING
            self.ws_thread = threading.Thread(target=self.ws_connection.run_forever, daemon=True)
            self.ws_thread.start()

            # Store channel type
            self.ws_channel_type = channel_type

            return True
        except Exception as e:
            print(f"WS connection failed: {e}")
            return False

    def subscribe_to_assets(self, assets: List[str], channel_type: str = "market"):
        """Subscribe to additional assets after connection."""
        if not self.ws_connection:
            print("WS not connected")
            return False

        try:
            msg = {
                "assets_ids": assets,
                "operation": "subscribe",
                "custom_feature_enabled": False
            }
            if channel_type == "user":
                msg["markets"] = assets

            self.ws_connection.send(json.dumps(msg))

            if channel_type == "user":
                self.subscribed_markets.update(assets)
            else:
                self.subscribed_assets.update(assets)

            return True
        except Exception as e:
            print(f"WS subscribe failed: {e}")
            return False

    def unsubscribe_from_assets(self, assets: List[str], channel_type: str = "market"):
        """Unsubscribe from assets."""
        if not self.ws_connection:
            return False

        try:
            msg = {
                "assets_ids": assets,
                "operation": "unsubscribe",
                "custom_feature_enabled": False
            }
            if channel_type == "user":
                msg["markets"] = assets

            self.ws_connection.send(json.dumps(msg))

            if channel_type == "user":
                self.subscribed_markets.difference_update(assets)
            else:
                self.subscribed_assets.difference_update(assets)

            return True
        except Exception as e:
            print(f"WS unsubscribe failed: {e}")
            return False

    def add_ws_callback(self, channel_type: str, callback: Callable):
        """Add callback function for websocket messages."""
        if channel_type not in self.ws_callbacks:
            self.ws_callbacks[channel_type] = []
        self.ws_callbacks[channel_type].append(callback)

    def close_websocket(self):
        """Close websocket connection."""
        if self.ws_connection:
            self.ws_connection.close()
            self.ws_connection = None
            self.ws_channel_type = None
            self.subscribed_markets.clear()
            self.subscribed_assets.clear()
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=1)



def test():
    host = "https://clob.polymarket.com"
    key = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
    print(key)
    chain_id = POLYGON

    # Create CLOB client and get/set API credentials
    client = ClobClient(host, key=key, chain_id=chain_id)
    client.set_api_creds(client.create_or_derive_api_creds())

    creds = ApiCreds(
        api_key=os.getenv("CLOB_API_KEY"),
        api_secret=os.getenv("CLOB_SECRET"),
        api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
    )
    chain_id = AMOY
    client = ClobClient(host, key=key, chain_id=chain_id, creds=creds)

    print(client.get_markets())
    print(client.get_simplified_markets())
    print(client.get_sampling_markets())
    print(client.get_sampling_simplified_markets())
    print(client.get_market("condition_id"))

    print("Done!")


def gamma():
    url = "https://gamma-com"
    markets_url = url + "/markets"
    res = httpx.get(markets_url)
    code = res.status_code
    if code == 200:
        markets: list[SimpleMarket] = []
        data = res.json()
        for market in data:
            try:
                market_data = {
                    "id": int(market["id"]),
                    "question": market["question"],
                    # "start": market['startDate'],
                    "end": market["endDate"],
                    "description": market["description"],
                    "active": market["active"],
                    "deployed": market["deployed"],
                    "funded": market["funded"],
                    # "orderMinSize": float(market['orderMinSize']) if market['orderMinSize'] else 0,
                    # "orderPriceMinTickSize": float(market['orderPriceMinTickSize']),
                    "rewardsMinSize": float(market["rewardsMinSize"]),
                    "rewardsMaxSpread": float(market["rewardsMaxSpread"]),
                    "volume": float(market["volume"]),
                    "spread": float(market["spread"]),
                    "outcome_a": str(market["outcomes"][0]),
                    "outcome_b": str(market["outcomes"][1]),
                    "outcome_a_price": str(market["outcomePrices"][0]),
                    "outcome_b_price": str(market["outcomePrices"][1]),
                }
                markets.append(SimpleMarket(**market_data))
            except Exception as err:
                print(f"error {err} for market {id}")
        pdb.set_trace()
    else:
        raise Exception()


def main():
    # auth()
    # test()
    # gamma()
    print(Polymarket().get_all_events())


if __name__ == "__main__":
    load_dotenv()

    p = Polymarket()

    # k = p.get_api_key()
    # m = p.get_sampling_simplified_markets()

    # print(m)
    # m = p.get_market('11015470973684177829729219287262166995141465048508201953575582100565462316088')

    def execute_market_sell(self, token_id: str, size: float) -> str:
        """
        Exits a position by placing a market-style (FOK) SELL order.
        """
        try:
            logger.info(f"Executing Market SELL for {token_id} (Size: {size})")
            
            # Place a limit order at $0.01 to act as a market sell
            # (This is a standard 'sweep' tactic to exit immediately)
            # We use py-clob-client's order builder constants if available, or string "SELL"
            try:
                from py_clob_client.order_builder.constants import SELL
                side = SELL
            except:
                side = "SELL"

            return self.place_limit_order(
                token_id=token_id, 
                price=0.01, # Sell at almost 0 to match any bid
                size=size, 
                side=side
            )
        except Exception as e:
            logger.error(f"Failed to execute market sell: {e}")
            return {"error": str(e)}

    # t = m[0]['token_id']
    # o = p.get_orderbook(t)
    # pdb.set_trace()

    """
    
    (Pdb) pprint(o)
            OrderBookSummary(
                market='0x26ee82bee2493a302d21283cb578f7e2fff2dd15743854f53034d12420863b55', 
                asset_id='11015470973684177829729219287262166995141465048508201953575582100565462316088', 
                bids=[OrderSummary(price='0.01', size='600005'), OrderSummary(price='0.02', size='200000'), ...
                asks=[OrderSummary(price='0.99', size='100000'), OrderSummary(price='0.98', size='200000'), ...
            )
    
    """

    # https://polygon-rpc.com

    test_market_token_id = (
        "101669189743438912873361127612589311253202068943959811456820079057046819967115"
    )
    test_market_data = p.get_market(test_market_token_id)

    # test_size = 0.0001
    test_size = 1
    test_side = BUY
    test_price = float(ast.literal_eval(test_market_data["outcome_prices"])[0])

    # order = p.execute_order(
    #    test_price,
    #    test_size,
    #    test_side,
    #    test_market_token_id,
    # )

    # order = p.execute_market_order(test_price, test_market_token_id)

    balance = p.get_usdc_balance()
