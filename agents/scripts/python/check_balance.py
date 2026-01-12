import sys
import os
from dotenv import load_dotenv

# Setup path to find the agents package
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../.."))

sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "agents"))

try:
    from agents.agents.polymarket.polymarket import Polymarket
except ImportError:
    try:
        from agents.polymarket.polymarket import Polymarket
    except ImportError:
        try:
           from polymarket.polymarket import Polymarket
        except ImportError:
            print("Could not import Polymarket client. Please check your python path.")
            sys.exit(1)

def main():
    load_dotenv()
    
    print("\n--------------------------------")
    print("💸 Checking Wallet Balance")
    print("--------------------------------")
    
    try:
        # Initialize client (this will try to load environment variables for keys)
        poly = Polymarket()
        
        # Get address and balance
        address = poly.get_address_for_private_key()
        balance = poly.get_usdc_balance()
        
        print(f"💳  Wallet Address: {address}")
        print(f"💰  USDC Balance:   ${balance:,.2f}")
        
    except Exception as e:
        print(f"❌  Error: {e}")
        print("Ensure POLYGON_WALLET_PRIVATE_KEY is set in your .env file")
    
    print("--------------------------------\n")

if __name__ == "__main__":
    main()
