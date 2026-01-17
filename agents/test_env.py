#!/usr/bin/env python3
"""
Test script to check environment variables in Fly.io
"""

import os

print("🔍 Environment Variables Check")
print("=" * 40)

# Check specific variables
pandascore_key = os.getenv("PANDASCORE_API_KEY")
print(f"PANDASCORE_API_KEY: {'SET' if pandascore_key else 'NOT SET'}")
if pandascore_key:
    print(f"  Length: {len(pandascore_key)}")
    print(f"  Preview: {pandascore_key[:10]}...")

# Check all env vars with 'panda' in them
panda_vars = {k: v for k, v in os.environ.items() if 'panda' in k.lower()}
print(f"\n🐼 Panda-related env vars: {list(panda_vars.keys())}")

# Check all secrets that should be set
secrets_to_check = [
    "PANDASCORE_API_KEY",
    "POLYGON_WALLET_PRIVATE_KEY",
    "POLYMARKET_PROXY_ADDRESS",
    "SUPABASE_URL"
]

print(f"\n🔐 Secrets Status:")
for secret in secrets_to_check:
    value = os.getenv(secret)
    status = "✅ SET" if value else "❌ NOT SET"
    print(f"  {secret}: {status}")
    if value and secret == "PANDASCORE_API_KEY":
        print(f"    Length: {len(value)}")
        print(f"    Preview: {value[:10]}...")