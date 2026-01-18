import os
import sys

# Add project root to sys.path
project_root = os.getcwd()
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv("agents/.env")

from agents.utils.supabase_client import get_supabase_state

def stop_remote():
    print("🛑 FORCE STOPPING SPORTS TRADER (REMOTE)...")
    try:
        supa = get_supabase_state()
        if supa:
            # "sport" is the db name for sports trader
            # We also set "sports_trader" just in case naming is inconsistent
            supa.set_agent_running("sport", False) 
            supa.set_agent_running("sports_trader", False)
            print("   ✅ Supabase state updated (Remote Stop)")
        else:
            print("   ⚠️ No Supabase client available.")
    except Exception as e:
        print(f"   ❌ Failed to stop via Supabase: {e}")

if __name__ == "__main__":
    stop_remote()
