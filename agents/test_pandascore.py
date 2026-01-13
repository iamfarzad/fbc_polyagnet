
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("PANDASCORE_API_KEY")

def test_pandascore():
    print("="*60)
    print("🐼 PANDASCORE API DIAGNOSTIC")
    print("="*60)
    
    if not API_KEY:
        print("❌ ERROR: PANDASCORE_API_KEY not found in environment.")
        print("   Please add it to your .env file.")
        return

    print(f"✅ API Key found: {API_KEY[:4]}...{API_KEY[-4:]}")
    
    games = ["csgo", "lol", "dota2"]
    total_live = 0
    
    for game in games:
        print(f"\nTesting {game.upper()} live matches...")
        try:
            url = f"https://api.pandascore.co/{game}/matches/running"
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Accept": "application/json"
            }
            
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                matches = resp.json()
                count = len(matches)
                total_live += count
                print(f"   ✅ Success! Found {count} live matches.")
                
                for m in matches:
                    match_id = m.get('id')
                    league = m.get('league', {}).get('name', 'Unknown')
                    opponents = m.get('opponents', [])
                    if len(opponents) >= 2:
                        t1 = opponents[0].get('opponent', {}).get('name')
                        t2 = opponents[1].get('opponent', {}).get('name')
                        print(f"      - [{match_id}] {league}: {t1} vs {t2}")
                    else:
                        print(f"      - [{match_id}] {league}: (Teams not defined)")
            elif resp.status_code == 401:
                print("   ❌ Authorization Failed (401). Check your API Key.")
            elif resp.status_code == 403:
                print("   ❌ Access Denied (403). Plan may not support this game/endpoint.")
            else:
                print(f"   ⚠️ API Error: {resp.status_code} - {resp.text}")
                
        except Exception as e:
            print(f"   ❌ Connection Error: {e}")

    print("\n" + "="*60)
    if total_live == 0:
        print("⚠️  Diagnosis: API works, but NO LIVE MATCHES found.")
        print("    The bot cannot trade if no games are live.")
    else:
        print(f"✅ Diagnosis: API works and found {total_live} live matches.")
    print("="*60)

if __name__ == "__main__":
    test_pandascore()
