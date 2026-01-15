"""
VERIFY DIRECT MODE
Checks if the agent environment is correctly configured for Direct Trading (No Proxy).
"""

import os
import sys
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

# We try to import the actual agent class to see how it initializes
try:
    sys.path.append(os.getcwd())
    from agents.agents.polymarket.polymarket import Polymarket
except ImportError:
    print("⚠️  Warning: Could not import Polymarket class. Using standalone checks.")
    Polymarket = None

def test_config():
    print("="*60)
    print("🕵️ AGENT CONFIGURATION TEST (Direct Mode)")
    print("="*60)

    # 1. Check Env Vars
    pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
    funder = os.getenv("POLYMARKET_FUNDER")
    sig_type = os.getenv("POLYMARKET_SIGNATURE_TYPE")

    print(f"1. Environment Variables:")
    print(f"   - Private Key: {'✅ Set' if pk else '❌ Missing'}")
    print(f"   - Funder (Proxy): {'❌ Set (Should be None for Direct)' if funder else '✅ Not Set (Correct)'}")
    print(f"   - Sig Type: {'❌ Set (Should be None)' if sig_type else '✅ Not Set (Correct)'}")

    if not pk:
        print("\n❌ CRITICAL: Private Key missing. Cannot proceed.")
        return

    # 2. Derive Address
    account = Account.from_key(pk)
    print(f"\n2. Identity Verification")
    print(f"   - Private Key resolves to: {account.address}")
    
    # 3. Initialize Agent Class (if possible)
    if Polymarket:
        try:
            print(f"\n3. Initializing Polymarket Agent...")
            agent = Polymarket()
            print(f"   - Agent Address: {agent.address}")
            print(f"   - Proxy Address: {agent.proxy_address}")
            
            if agent.proxy_address is None or agent.proxy_address == agent.address:
                 print("   ✅ CORRECT: Agent is NOT using a Proxy.")
            else:
                 print(f"   ❌ WARNING: Agent thinks it has a proxy: {agent.proxy_address}")

            # Check Balance
            print(f"\n4. Checking Shared Funds (USDC)...")
            balance = agent.get_usdc_balance()
            print(f"   - Balance: ${balance:,.2f}")
            
            if balance > 0:
                print("   ✅ Funds detected! Agents can trade. 💸")
            else:
                print("   ⚠️  Balance is 0. Agents will starve.")

        except Exception as e:
            print(f"   ❌ Agent Init Failed: {e}")
    else:
        print("\n3. Skipping Agent Init check (Import failed)")

    # 5. Test Signing (Ability to Trade)
    print(f"\n5. Testing Signing Capability...")
    try:
        msg = "Verify Direct Mode"
        # Use encode_defunct for standard EIP-191 signing
        message = encode_defunct(text=msg)
        signed = Account.sign_message(message, private_key=pk)
        print(f"   ✅ Signature Generated Successfully!")
        print(f"   - Sig: {signed.signature.hex()[:20]}...")
        print("   (This confirms the bot can sign trades directly)")
    except Exception as e:
        print(f"   ❌ Signing Failed: {e}")
        
    print("\n" + "="*60)
    print("✅ VERIFICATION COMPLETE")
    print("="*60)

if __name__ == "__main__":
    test_config()
