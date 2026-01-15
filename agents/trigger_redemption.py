
import sys
import os

# Add agents dir to path
sys.path.append(os.getcwd())

try:
    from agents.utils.auto_redeem import AutoRedeemer
    
    print("Initializing AutoRedeemer...")
    redeemer = AutoRedeemer()
    
    print(f"Scanning for redeemable positions on {redeemer.address}...")
    result = redeemer.scan_and_redeem()
    
    print(f"Redemption Scan Complete.")
    print(f"Result: {result}")
    
except Exception as e:
    print(f"Error running redemption: {e}")
