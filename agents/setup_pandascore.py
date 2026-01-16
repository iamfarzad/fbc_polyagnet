#!/usr/bin/env python3
"""
Pandascore API Setup Helper for Esports Trading Bot

This script helps you get and configure your Pandascore API key
for profitable esports trading instead of losing money.
"""

import os
import sys
import requests

def test_pandascore_key(api_key: str) -> bool:
    """Test if the Pandascore API key works."""
    try:
        url = "https://api.pandascore.co/lol/matches/running"
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ API key works! Found {len(data)} live LoL matches")
            return True
        elif response.status_code == 401:
            print("❌ Invalid API key")
            return False
        else:
            print(f"❌ API error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def main():
    print("🎮 Pandascore API Setup for Esports Trading Bot")
    print("=" * 50)
    print()

    # Check current status
    current_key = os.getenv("PANDASCORE_API_KEY")
    if current_key:
        print("📋 Current API key found")
        if test_pandascore_key(current_key):
            print("✅ Your API key is working! Esports trading should now be profitable.")
            print("\n💡 Restart your esports trader: fly machines restart [machine-id]")
            return
        else:
            print("❌ Current API key is invalid")
    else:
        print("📋 No API key currently configured")

    print("\n🚀 SETUP INSTRUCTIONS:")
    print("1. Go to https://pandascore.co/users/sign_up")
    print("2. Create a free account")
    print("3. Go to https://pandascore.co/settings/api-keys")
    print("4. Generate a new API key")
    print("5. Copy the key below")
    print()

    # Get new key from user
    api_key = input("Enter your Pandascore API key: ").strip()

    if not api_key:
        print("❌ No API key provided")
        return

    # Test the key
    print("\n🔍 Testing API key...")
    if test_pandascore_key(api_key):
        print("\n✅ SUCCESS! API key is valid.")
        print("\n📝 To save this key permanently:")
        print("1. For local development, add to your .env file:")
        print(f"   PANDASCORE_API_KEY={api_key}")
        print()
        print("2. For Fly.io deployment:")
        print(f"   fly secrets set PANDASCORE_API_KEY={api_key}")
        print()
        print("3. Restart your esports trader:")
        print("   fly machines restart [your-esports-machine-id]")
        print()
        print("🎯 Your esports bot will now make profitable trades using live game data!")
    else:
        print("\n❌ API key test failed. Please check your key and try again.")
        print("💡 Make sure you're using the correct key from pandascore.co")

if __name__ == "__main__":
    main()