import os
import sys
from dotenv import load_dotenv
from eth_account import Account

# Load env
load_dotenv("agents/.env")

pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
proxy = os.getenv("POLYMARKET_PROXY_ADDRESS")

if not pk:
    print("No Private Key found!")
    sys.exit(1)

account = Account.from_key(pk)
eoa = account.address

print(f"EOA Address (from PK): {eoa}")
print(f"Proxy Address (from .env): {proxy}")

# Check which one was used in the ledger report
ledger_address = "0x3C5179f63E580c890950ac7dfCf96e750fB2D046" # From full_ledger.md
print(f"Address in full_ledger.md: {ledger_address}")

if eoa.lower() == ledger_address.lower():
    print("MATCH: Ledger scanned the EOA.")
elif proxy and proxy.lower() == ledger_address.lower():
    print("MATCH: Ledger scanned the Proxy.")
else:
    print("MISMATCH: Ledger scanned an unknown address.")
