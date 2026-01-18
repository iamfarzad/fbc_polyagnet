import os
import sys
import json
from dotenv import load_dotenv

project_root = os.getcwd()
sys.path.insert(0, project_root)
load_dotenv("agents/.env")

from agents.polymarket.polymarket import Polymarket

def cancel_west_illinois():
    print("🗑️ CANCELLING WESTERN ILLINOIS ORDERS...")
    pm = Polymarket()
    
    try:
        # Get orders - patched method
        orders = pm.get_open_orders()
        print(f"   📋 Found {len(orders)} open orders.")
        
        cancelled = 0
        for o in orders:
            # We need to identify if it's Western Illinois
            # 'o' might be a dict or object
            # If we can't see the market name easily, we might have to fetch it or guess
            # But the user sent a screenshot showing "Buy Western Illinois Leathernecks"
            
            # Polymarket API orders usually have a 'market' or 'token_id' field.
            # If we don't have the question string, we'll have to fetch market details for each order.
            
            token_id = ""
            order_id = ""
            
            if hasattr(o, 'id'):
                order_id = o.id
                token_id = o.token_id
            else:
                order_id = o.get('orderID') or o.get('id')
                token_id = o.get('asset_id') or o.get('token_id')
                
            if not token_id: continue

            # Fetch market
            try:
                m = pm.get_market(token_id)
                # Check for "Western Illinois" in question or outcomes
                # ROBUST ACCESS
                q_text = ""
                try:
                    # Try attribute access first
                    q_text = str(getattr(m, 'question', '')) + " " + str(getattr(m, 'outcomes', ''))
                except:
                    pass
                
                if not q_text.strip():
                    # Try dict access
                    try:
                        q_text = str(m.get('question', '')) + " " + str(m.get('outcomes', ''))
                    except:
                        pass
                
                print(f"      Checked Type: {type(m)} -> Q: {q_text[:20]}...")

                if "Western Illinois" in q_text or "Leathernecks" in q_text:
                    print(f"      ❌ Found Rogue Order: {m.question} (ID: {order_id})")
                    pm.client.cancel_order(order_id)
                    cancelled += 1
            except Exception as ex:
                print(f"      ⚠️ Failed to check order {order_id}: {ex}")
                continue
                
        if cancelled > 0:
            print(f"   ✅ Cancelled {cancelled} orders.")
        else:
            print("   ℹ️ No matching orders found.")
            
    except Exception as e:
        print(f"   ❌ Error cancelling: {e}")

if __name__ == "__main__":
    cancel_west_illinois()
