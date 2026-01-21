
import os
import sys
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

# Add parent path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)
env_path = os.path.join(base_dir, "agents", ".env")
print(f"Loading env from: {env_path}")
load_dotenv(env_path)

print(f"DEBUG: SUPABASE_URL = {str(os.getenv('SUPABASE_URL'))[:10]}...")
print(f"DEBUG: SUPABASE_SERVICE_KEY = {str(os.getenv('SUPABASE_SERVICE_KEY'))[:10]}...")

from agents.utils.supabase_client import get_supabase_state


import requests

def analyze_losses():
    supa = get_supabase_state()
    
    # Check credentials
    if not supa.url or not supa.key:
        print("❌ Missing Supabase credentials in env vars.")
        return

    # Narrow window around the trades (20:16 UTC)
    start_time = "2026-01-19T19:00:00"
    end_time = "2026-01-19T21:00:00"
    
    headers = {
        "apikey": supa.key,
        "Authorization": f"Bearer {supa.key}",
        "Content-Type": "application/json"
    }
    
    # REST Query: agent=eq.esports_trader & created_at >= start & created_at <= end
    # Note: PostgREST uses specific syntax for filters
    url = f"{supa.url}/rest/v1/llm_activity"
    
    query_string = f"?agent=eq.esports_trader&created_at=gte.{start_time}&created_at=lte.{end_time}&select=*&order=created_at.asc"
    full_url = url + query_string
    
    print(f"   Getting logs from: {full_url}")
    
    try:
        response = requests.get(full_url, headers=headers)
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code} - {response.text}")
            return
            
        logs = response.json()
        print(f"   Found {len(logs)} logs.")
        
        print(f"\n🚨 LOGS FROM WINDOW ({start_time} - {end_time}):")
        
        for log in logs:
            ts = log.get('created_at', '')
            action = log.get('action_type', 'UNKNOWN')
            conf = log.get('confidence', 0)
            q = log.get('market_question', '')
            reason = log.get('reasoning', '')
            
            # Print only non-heartbeat to reduce noise
            if action != "heartbeat":
                print(f"[{ts}] {action} (Conf: {conf})")
                print(f"   Q: {q}")
                print(f"   Reasoning: {reason}")
                print("-" * 60)
            
    except Exception as e:
        print(f"Error querying logs: {e}")

if __name__ == "__main__":
    analyze_losses()
