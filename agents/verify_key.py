
from eth_account import Account
import os
from dotenv import load_dotenv

load_dotenv()
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
if pk:
    try:
        acct = Account.from_key(pk)
        print(f"Current .env Key Address: {acct.address}")
    except Exception as e:
        print(f"Error deriving address: {e}")
else:
    print("No key found")
