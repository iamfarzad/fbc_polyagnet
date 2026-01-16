import requests
import json

def find_tags():
    print("🔍 1. Scouring Tags...")
    try:
        url = "https://gamma-api.polymarket.com/tags"
        params = {"limit": 1000}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        tags = resp.json()
        
        print(f"   ℹ️ Total tags fetched: {len(tags)}")
        if len(tags) > 0:
            print(f"   ℹ️ Sample Tag 0: {json.dumps(tags[0], indent=2)}")
        
        keywords = ['crypto', '15-minute', 'price', 'hft']
        found_tags = []
        
        for t in tags:
            # Check structure based on sample
            label = str(t.get('label', '')).lower()
            slug = str(t.get('slug', '')).lower()
            # Also check 'name' if it exists
            name = str(t.get('name', '')).lower()
            
            if any(k in label or k in slug or k in name for k in keywords):
                found_tags.append(t)
                print(f"   found tag: {t}")
                
    except Exception as e:
        print(f"   ❌ Error fetching tags: {e}")

    print("\n🔍 3. Inspecting Tag 1006 Directly...")
    try:
        url = "https://gamma-api.polymarket.com/tags/1006"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            print(f"   ✅ Tag 1006 Found: {json.dumps(resp.json(), indent=2)}")
        else:
            print(f"   ❌ Tag 1006 Lookup Failed: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error fetching Tag 1006: {e}")

    print("\n🔍 5. Searching Tags by Slug & Closed Markets...")
    
    # 5a. Try slug lookup
    slugs = ["crypto", "bitcoin", "ethereum", "15-minute", "hft"]
    for s in slugs:
        try:
           # Guessing endpoint based on common REST patterns
           # Try filtering list
           url = "https://gamma-api.polymarket.com/tags"
           params = {"slug": s}
           resp = requests.get(url, params=params, timeout=5)
           tags = resp.json()
           if tags:
               print(f"   ✅ Found Tag by slug '{s}': {json.dumps(tags, indent=2)}")
        except: pass

    # 5b. Search CLOSED markets (History)
    try:
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "active": "false", # Check CLOSED markets 
            "closed": "true",
            "limit": 50,
            "offset": 0
        }
        
        print(f"      Scanning CLOSED markets...")
        markets_checked = 0
        while markets_checked < 500:
            resp = requests.get(url, params=params, timeout=10)
            markets = resp.json()
            if not markets: break
            
            for m in markets:
                q = m.get('question', '').lower()
                if 'bitcoin' in q and 'up or down' in q:
                    tags = m.get('tags')
                    if tags:
                        print(f"   ✅ Found HISTORICAL Market: {m.get('question')}")
                        print(f"      Tags: {json.dumps(tags, indent=2)}")
                        return # Found it
                markets_checked += 1
            
            params["offset"] += 50
            
    except Exception as e:
        print(f"   ❌ Error searching closed markets: {e}")

    print("\n🔍 4. Finding 'Bitcoin'/'Ethereum' Markets (Deep Search)...")
    try:
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "active": "true", 
            "limit": 100,
            "closed": "false",
            "offset": 0
        }
        
        found_crypto_market = False
        markets_checked = 0
        
        while markets_checked < 2000:
            print(f"      Fetching offset {params['offset']}...")
            resp = requests.get(url, params=params, timeout=10)
            markets = resp.json()
            
            if not markets: break
            
            for m in markets:
                markets_checked += 1
                q = m.get('question', '').lower()
                if 'bitcoin' in q or 'ethereum' in q:
                    tags = m.get('tags')
                    if not tags: continue # Skip if no tags
                    
                    found_crypto_market = True
                    print(f"   ✅ Found Market: {m.get('question')}")
                    print(f"      Tags: {json.dumps(tags, indent=2)}")
                    
                    # Check if any tag looks like 'crypto' or '15'
                    for t in tags:
                         if 'crypto' in str(t).lower() or '15' in str(t).lower():
                             print(f"      🎯 POTENTIAL MATCH: {t}")
                    
                    if markets_checked % 5 == 0: break 
                    
            if found_crypto_market and markets_checked > 200: # Scan at least a few matches
                break
                
            params["offset"] += 100
                
    except Exception as e:
        print(f"   ❌ Error fetching specific markets: {e}")

if __name__ == "__main__":
    find_tags()
