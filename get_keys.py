import os
import sys
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# Load environment variables from agents directory
sys.path.append('agents')
load_dotenv('agents/.env')

def get_clob_keys():
    private_key = os.getenv("POLYGON_WALLET_PRIVATE_KEY")

    if not private_key:
        print("Error: POLYGON_WALLET_PRIVATE_KEY not found in environment")
        print("Checking all environment variables containing 'POLYGON'...")
        for key, value in os.environ.items():
            if 'POLYGON' in key.upper():
                print(f"  {key}: {value[:10]}...")
        return

    # Initialize client (Chain ID 137 for Polygon Mainnet)
    client = ClobClient(
        "https://clob.polymarket.com",
        key=private_key,
        chain_id=POLYGON
    )

    # This function generates or retrieves the existing keys for your wallet
    creds = client.create_or_derive_api_creds()

    print("\n=== Your Polymarket CLOB API Credentials ===")
    print(f"API Key:      {creds.api_key}")
    print(f"Secret:       {creds.api_secret}")
    print(f"Passphrase:   {creds.api_passphrase}")
    print("==========================================\n")

if __name__ == "__main__":
    get_clob_keys()