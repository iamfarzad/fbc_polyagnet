import os
import sys
import requests
import json
from dotenv import load_dotenv

# Setup path
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
         # Fallback manual keys if import fails (unlikely now)
         pass

def main():
    load_dotenv()
    
    try:
        poly = Polymarket()
        address = poly.get_address_for_private_key()
        print(f"Address: {address}")
        
        # specific endpoint for activity
        url = f"https://data-api.polymarket.com/activity?user={address}&limit=20&offset=0"
        resp = requests.get(url)
        data = resp.json()
        
        print("--- Activity Sample ---")
        print(json.dumps(data[:3], indent=2))
        
        # Check for unique types
        types = set(d.get('type') for d in data)
        print(f"\nActivity Types found: {types}")

        # Check for unique sides
        sides = set(d.get('side') for d in data)
        print(f"Activity Sides found: {sides}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
