import requests
import json

def verify_slugs():
    slugs = ["crypto", "bitcoin", "ethereum", "15-minute", "hft", "price"]
    print(f"🔍 Checking Slugs: {slugs}")
    
    for s in slugs:
        try:
           url = "https://gamma-api.polymarket.com/tags"
           params = {"slug": s}
           resp = requests.get(url, params=params, timeout=5)
           tags = resp.json()
           if tags:
               print(f"   ✅ Slug '{s}': {json.dumps(tags, indent=2)}")
           else:
               print(f"   ❌ Slug '{s}': Not Found")
        except Exception as e:
            print(f"   ⚠️ Error '{s}': {e}")
            
    # Check ID 1, 100, 1000 just in case
    ids = [1, 2, 100, 21] # 21 (Bitcoin usually?)
    print(f"\n🔍 Checking IDs: {ids}")
    for i in ids:
        try:
           url = f"https://gamma-api.polymarket.com/tags/{i}"
           resp = requests.get(url, timeout=5)
           if resp.status_code == 200:
               print(f"   ✅ ID {i}: {json.dumps(resp.json(), indent=2)}")
        except: pass

if __name__ == "__main__":
    verify_slugs()
