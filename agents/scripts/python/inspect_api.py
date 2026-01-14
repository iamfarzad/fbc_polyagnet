import os
import sys
import requests
from dotenv import load_dotenv
import json

# Setup path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../.."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "agents"))

from agents.polymarket.polymarket import Polymarket

load_dotenv()
poly = Polymarket()
address = poly.get_address_for_private_key()

url = f"https://data-api.polymarket.com/activity?user={address}&limit=1"
try:
    resp = requests.get(url)
    data = resp.json()
    if data:
        print(json.dumps(data[0], indent=2))
    else:
        print("No activity found")
except Exception as e:
    print(e)
