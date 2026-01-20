"""
Universal Sports Trader - Math + Intelligence 🏀⚽️
Uses The Odds API for Fair Price & Perplexity for Risk Management.
"""
import os
import sys
import time
import json
import requests
import datetime
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.polymarket.polymarket import Polymarket
from agents.utils.validator import Validator, SharedConfig
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
from agents.utils.context import get_context, Position, Trade

# Try to import auto-redeemer
try:
    from agents.utils.auto_redeem import AutoRedeemer
    HAS_REDEEMER = True
except ImportError:
    HAS_REDEEMER = False
    AutoRedeemer = None

# Import Supabase state manager
try:
    from agents.utils.supabase_client import get_supabase_state
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    get_supabase_state = None

load_dotenv()

# --- CONFIGURATION (DEFAULTS) ---
DEFAULT_MIN_BET = 5.00
DEFAULT_MAX_BET = 10.00
DEFAULT_BET_PCT = 0.15
DEFAULT_MIN_CONF = 0.55
DEFAULT_SCAN_INTERVAL = 60

# --- NEW INTELLIGENCE IMPORTS ---
from agents.utils.config import load_config
from agents.application.smart_context import SmartContext

# Polymarket Sports Series IDs (for direct Gamma API)
SPORTS_SERIES = {
    "NBA": 10345,
    "NFL": 10346,
    "MLB": 10347, # Using 10347 based on user input, though user said MLB is 10347 under US Sports but soccer also 10347? Wait. 
    # User said: MLB (10347). Soccer (EPL: 10351, etc). Let's stick to what user provided for Major US Sports.
    # Actually user listed MLB (10347) but also listed Soccer (10347 is not listed for soccer, 10347 was General Soccer in my previous code but user says MLB).
    # Let's follow user's explicit list:
    "NBA": 10345,
    "NFL": 10346,
    "MLB": 10347,
    "NHL": 10348,
    "EPL": 10351,
    "Serie A": 10353,
    "La Liga": 10352,
    "Champions League": 10355,
    "MLS": 10354,
    "Tennis": 10359,
    "UFC": 10357,
}

# Tag ID for game-specific bets (not futures)
GAME_TAG_ID = 100639

# --- CONTRARIAN SYSTEM PROMPT ---
RISK_MANAGER_PROMPT = """You are a contrarian sports bettor and risk manager.
Your GOAL is to find reasons NOT to bet on the favorite.

For the requested matchup, perform these specific checks:
1. INJURY SEARCH: Search explicitly for "[Team Name] injury report today". If a Star Player is "Out" or "Questionable", DEDUCT 15% from their win probability immediately.
2. SCHEDULE SPOT: Check if the favorite is on a "back-to-back" or playing their 3rd game in 4 nights. If yes, this is a "Trap Game".
3. MOMENTUM CHECK: Search for "last 5 games record". If the Favorite has lost 3+ of last 5, they are "Cold".

OUTPUT "PASS" IF:
- A key player is injured for the favorite.
- The favorite is on a losing streak (3+ losses).
- The team is tired (Back-to-back).

Only recommend "BET" if the team is healthy, rested, and in form."""

class SportsTrader:
    AGENT_NAME = "sports_trader"

    def __init__(self, dry_run=True):
        # Load Config
        self.config = load_config("sports_trader")
        self.dry_run = dry_run or self.config.get("global_dry_run", False)
        
        # Intelligence Layer
        self.smart_context = SmartContext()
        
        self.pm = Polymarket()
        self.validator = Validator(SharedConfig(), agent_name=self.AGENT_NAME)
        
        # Config Values with defaults
        self.min_bet = self.config.get("min_bet", DEFAULT_MIN_BET)
        self.max_bet = self.config.get("max_bet", DEFAULT_MAX_BET)
        self.bet_pct = self.config.get("bet_size_percent", DEFAULT_BET_PCT)
        self.min_conf = self.config.get("min_confidence", DEFAULT_MIN_CONF)
        self.scan_interval = self.config.get("scan_interval", DEFAULT_SCAN_INTERVAL)

        # Initialize Shared Context with robust import check
        try:
            from agents.utils.context import get_context, LLMActivity
            self.context = get_context()
            self.LLMActivity = LLMActivity
        except ImportError:
            try: 
                from agents.utils.context import get_context, LLMActivity
                self.context = get_context()
                self.LLMActivity = LLMActivity
            except:
                self.context = None
                self.LLMActivity = None

        
        # State
        self.positions = {}
        self.trades_made = 0
        self.total_invested = 0.0
        
        # Balance
        try:
            self.balance = self.pm.get_usdc_balance()
        except:
            self.balance = 0
        
        # Auto-Redeemer
        self.redeemer = AutoRedeemer() if HAS_REDEEMER else None

        print(f"="*60)
        print(f"🏟️ SPORTS TRADER - Direct Polymarket Mode")
        print(f"="*60)
        print(f"Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE'}")
        print(f"Data Source: Polymarket Gamma API (NO external API needed)")
        print(f"Scan Interval: {self.scan_interval}s")
        print(f"Balance: ${self.balance:.2f}")

        # Self-Learning State
        self.last_learning_time = 0
        self.LEARNING_INTERVAL = 3600 * 4  # Run analysis every 4 hours

    def run_learning_cycle(self):
        """Run post-trade analysis to learn from mistakes."""
        # Late import to avoid circular dependencies if any
        try:
            from agents.utils.mistake_analyzer import MistakeAnalyzer
            analyzer = MistakeAnalyzer(agent_name=self.AGENT_NAME) 
        except ImportError:
            return

        now = time.time()
        if now - self.last_learning_time > self.LEARNING_INTERVAL:
            try:
                print("   🧠 Starting Self-Learning Cycle...")
                lessons = analyzer.analyze_completed_trades(limit=5)
                if lessons:
                    print(f"   🎓 Learned {len(lessons)} new lessons from recent trades.")
                else:
                    print("   🧠 No new lessons to learn this cycle.")
                self.last_learning_time = now
            except Exception as e:
                print(f"   ⚠️ Self-learning cycle failed: {e}")

    def _state_file_paths(self) -> List[str]:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return [
            os.path.join(base_dir, "bot_state.json"),
            os.path.join(os.path.dirname(base_dir), "bot_state.json")
        ]

    def _load_local_state(self) -> Dict:
        for path in self._state_file_paths():
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        return json.load(f)
                except Exception:
                    continue
        return {}

    def _is_locally_running(self) -> bool:
        state = self._load_local_state()
        if not state:
            return True
        return state.get("sports_trader_running", True)

    def get_live_polymarket_sports(self, series_id: int = None) -> List[Dict]:
        """
        Fetch LIVE sports markets directly from Polymarket Gamma API.
        No external API needed - sees exactly what's on polymarket.com/sports/live
        """
        try:
            # Build URL with optional series filter
            base_url = "https://gamma-api.polymarket.com/events"
            params = {
                "active": "true",
                "closed": "false",
                "tag_id": GAME_TAG_ID,  # 100639 = game-specific bets
                "limit": 50,
            }
            if series_id:
                params["series_id"] = series_id
            
            resp = requests.get(base_url, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"   ⚠️ Gamma API Error: {resp.status_code}")
                return []
            
            events = resp.json()
            markets = []
            
            for event in events:
                # Get the markets within this event
                event_markets = event.get("markets", [])
                if not event_markets:
                    continue
                
                for m in event_markets:
                    # Parse token IDs
                    clob_ids = m.get("clobTokenIds", "[]")
                    try:
                        import ast
                        tokens = ast.literal_eval(clob_ids) if isinstance(clob_ids, str) else clob_ids
                        if len(tokens) < 2:
                            continue
                    except:
                        continue
                    
                    # Parse prices
                    outcomes = m.get("outcomePrices", "[0.5, 0.5]")
                    if isinstance(outcomes, str):
                        outcomes = ast.literal_eval(outcomes)
                    
                    yes_price = float(outcomes[0]) if outcomes else 0.5
                    no_price = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_price
                    
                    markets.append({
                        "id": m.get("id"),
                        "question": m.get("question", event.get("title", "")),
                        "event_title": event.get("title", ""),
                        "yes_token": tokens[0],
                        "no_token": tokens[1],
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "volume": float(m.get("volume24hr", 0) or 0),
                        "liquidity": float(m.get("liquidity", 0) or 0),
                        "end_date": m.get("endDate", ""),
                        "slug": m.get("slug", ""),
                        "accepting_orders": m.get("acceptingOrders", False),
                    })
            
            return markets
            
        except Exception as e:
            print(f"   Error fetching Polymarket sports: {e}")
            return []

    def find_polymarket_match(self, home_team: str, away_team: str, sport_config: dict) -> Optional[Dict]:
        """
        Finds the correct Polymarket Event ID using fuzzy matching (difflib).
        """
        import difflib
        
        # 1. Fetch active events from Polymarket Gamma API
        url = "https://gamma-api.polymarket.com/events?closed=false&limit=100&active=true" 
        try:
            # In a real production app, we should cache this response to avoid hitting rate limits
            response = requests.get(url, timeout=10).json()
        except Exception as e:
            print(f"      ⚠️ Error fetching Polymarket events: {e}")
            return None

        # 2. Filter for the right sport
        #    We look for keywords in the event title (e.g. "NBA", "Celtics")
        #    We can use the teams themselves as keywords
        relevant_events = []
        for e in response:
            title = e.get('title', '')
            # Check if either team name is in the title
            if home_team in title or away_team in title:
                relevant_events.append(e)
            # Or if the sport key is in the title (simplified)
            elif sport_config.get('key').split('_')[-1].upper() in title: 
                 relevant_events.append(e)

        if not relevant_events:
            return None

        # 3. Create a search string for our game
        #Standard Polymarket format is often "Team A vs Team B" or "Will Team A beat Team B?"
        my_game_str = f"{away_team} vs {home_team}"
        
        # 4. Fuzzy Match using difflib
        best_match = None
        best_score = 0.0
        
        for e in relevant_events:
            title = e.get('title', '')
            # Compare my_game_str to the title
            ratio = difflib.SequenceMatcher(None, my_game_str.lower(), title.lower()).ratio()
            
            # Also check reversed order just in case
            my_game_str_rev = f"{home_team} vs {away_team}"
            ratio_rev = difflib.SequenceMatcher(None, my_game_str_rev.lower(), title.lower()).ratio()
            
            score = max(ratio, ratio_rev)
            
            if score > best_score:
                best_score = score
                best_match = e
        
        if best_score > 0.6: # Confidence threshold (lower than 85 because titles vary wildy)
            print(f"      🔗 Linked: '{my_game_str}' ↔ '{best_match['title']}' (Score: {best_score:.2f})")

            if 'markets' in best_match:
                # Find the best market within this event
                for market in best_match['markets']:
                    # Look for markets that match our teams or are winner/moneyline markets
                    question = market.get('question', '').lower()
                    if any(team.lower() in question for team in [home_team, away_team]) or \
                       'winner' in question or 'moneyline' in question or 'win' in question:
                        # Extract token IDs properly (same as get_live_polymarket_sports)
                        clob_ids = market.get("clobTokenIds", "[]")
                        try:
                            import ast
                            tokens = ast.literal_eval(clob_ids) if isinstance(clob_ids, str) else clob_ids
                            if len(tokens) >= 2:
                                # Parse prices
                                outcomes = market.get("outcomePrices", "[0.5, 0.5]")
                                if isinstance(outcomes, str):
                                    outcomes = ast.literal_eval(outcomes)

                                yes_price = float(outcomes[0]) if outcomes else 0.5
                                no_price = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_price

                                # Return properly formatted market dict
                                return {
                                    "id": market.get("id"),
                                    "question": market.get("question", best_match['title']),
                                    "event_title": best_match['title'],
                                    "yes_token": tokens[0],
                                    "no_token": tokens[1],
                                    "yes_price": yes_price,
                                    "no_price": no_price,
                                    "volume": float(market.get("volume24hr", 0) or 0),
                                    "liquidity": float(market.get("liquidity", 0) or 0),
                                    "end_date": market.get("endDate", ""),
                                    "slug": market.get("slug", ""),
                                }
                        except Exception as e:
                            print(f"      ⚠️ Failed to parse market tokens: {e}")
                            continue

                # Fallback: return first market if no specific match found
                market = best_match['markets'][0]
                clob_ids = market.get("clobTokenIds", "[]")
                try:
                    import ast
                    tokens = ast.literal_eval(clob_ids) if isinstance(clob_ids, str) else clob_ids
                    if len(tokens) >= 2:
                        outcomes = market.get("outcomePrices", "[0.5, 0.5]")
                        if isinstance(outcomes, str):
                            outcomes = ast.literal_eval(outcomes)
                        yes_price = float(outcomes[0]) if outcomes else 0.5
                        no_price = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_price

                        return {
                            "id": market.get("id"),
                            "question": market.get("question", best_match['title']),
                            "event_title": best_match['title'],
                            "yes_token": tokens[0],
                            "no_token": tokens[1],
                            "yes_price": yes_price,
                            "no_price": no_price,
                            "volume": float(market.get("volume24hr", 0) or 0),
                            "liquidity": float(market.get("liquidity", 0) or 0),
                            "end_date": market.get("endDate", ""),
                            "slug": market.get("slug", ""),
                        }
                except Exception as e:
                    print(f"      ⚠️ Failed to parse fallback market: {e}")

            return {"id": best_match['id'], "question": best_match['title']} # Fallback
            
        return None

    def execute_bet(self, market: Dict, side: str, size: float, price: float):
        """Execute trade on Polymarket with real CLOB integration."""
        question = market.get('question', 'Unknown Sports Market')
        market_id = market.get('id')

        # Identify correct token based on side (YES or NO)
        if side.upper() == "YES":
            token_id = market.get('yes_token')
        elif side.upper() == "NO":
            token_id = market.get('no_token')
        else:
            # Fallback to clobTokenIds if side format is unexpected
            token_id = market.get('yes_token') or market.get('clobTokenIds', [None, None])[0]

        if not token_id:
            print(f"      ❌ Failed to execute: No Token ID found for {question} (side: {side})")
            return

        print(f"      💰 EXECUTING: {side} on '{question}' @ {price:.2f} (Amt: ${size:.2f})")

        if self.dry_run:
            print(f"      [DRY RUN] Trade logged.")
            self.trades_made += 1
            return

        try:
            # SECURITY: Hard Cap Enforcement
            if size > 5.0:
                print(f"      ⚠️ Capping bet size to $5.00 (was ${size:.2f})")
                size = 5.0

            order_args = OrderArgs(
                token_id=str(token_id),
                price=round(price + 0.01, 2), # Add 1c buffer for sports fills
                size=size / price,
                side=BUY
            )

            signed = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed)

            if result.get("success") or result.get("status") == "matched":
                print(f"      ✅ LIVE ORDER FILLED!")
                self.trades_made += 1
                self.total_invested += size

                # Refresh balance after successful trade
                try:
                    self.balance = self.pm.get_usdc_balance()
                except:
                    pass

                # Record in Shared Context
                self.context.add_position(Position(
                    market_id=market_id,
                    market_question=question,
                    agent=self.AGENT_NAME,
                    outcome=side,
                    entry_price=price,
                    size_usd=size,
                    timestamp=datetime.datetime.now().isoformat(),
                    token_id=token_id
                ))
            else:
                error_msg = result.get('error', result.get('status', 'Unknown error'))
                if 'allowance' in str(error_msg).lower() or 'balance' in str(error_msg).lower():
                    print(f"      🚫 ALLOWANCE ISSUE: {error_msg}")
                    print(f"      💡 You may need to approve USDC spending on Polymarket")
                else:
                    print(f"      ⚠️ Order failed: {error_msg}")

        except Exception as e:
            error_str = str(e)
            if 'allowance' in error_str.lower() or 'balance' in error_str.lower():
                print(f"      🚫 ALLOWANCE/BALANCE ISSUE: {e}")
                print(f"      💡 Check: 1) USDC balance on Polymarket, 2) Contract allowance approved")
            else:
                print(f"      ❌ Execution Error: {e}")

    def scan_live_markets(self):
        """
        Scan live Polymarket sports directly using Gamma API.
        No external API needed - trades based on what's actually live.
        """
        print(f"\n🌍 SCANNING POLYMARKET LIVE SPORTS...")

        # Refresh balance before scanning
        try:
            self.balance = self.pm.get_usdc_balance()
            print(f"   💰 Current balance: ${self.balance:.2f}")
        except Exception as e:
            print(f"   ⚠️ Balance check failed: {e}")

        # Fetch all live sports markets
        all_markets = self.get_live_polymarket_sports()

        # Filter for markets that are accepting orders
        markets = [m for m in all_markets if m.get("accepting_orders", False)]

        if not markets:
            print(f"   📡 Found {len(all_markets)} live markets, but none are accepting orders.")
            return

        print(f"   📡 Found {len(markets)} tradeable markets (accepting orders)")

        # CRITICAL FIX: Fetch open orders to prevent duplicate betting
        try:
            open_orders = self.pm.get_open_orders()
            # extract questions or token IDs from open orders
            open_order_token_ids = set()
            for o in open_orders:
                tid = o.get('asset_id') or o.get('token_id')
                if tid: open_order_token_ids.add(str(tid))
            
            # ALSO fetch positions to prevent re-betting on filled orders
            positions = self.pm.get_positions() # Returns list of positions
            for p in positions:
                tid = p.get('asset_id') or p.get('tokenId')
                # only block if size > 0
                if float(p.get('size', 0)) > 0:
                    if tid: open_order_token_ids.add(str(tid))

            print(f"   🔒 {len(open_orders)} open orders + {len(positions)} held positions detected (skipping these markets)")
        except Exception as e:
            print(f"   ⚠️ Failed to fetch open orders/positions: {e}")
            open_order_token_ids = set()

        trades_this_scan = 0
        max_trades_per_scan = 1  # Only allow 1 trade per scan cycle

        for market in markets:
            if trades_this_scan >= max_trades_per_scan:
                print(f"   ⏸️  Reached max trades per scan ({max_trades_per_scan}). Stopping.")
                break
                
            # Check if we already have an open order for this market's tokens
            yes_tok = str(market.get("yes_token", ""))
            no_tok = str(market.get("no_token", ""))
            
            if yes_tok in open_order_token_ids or no_tok in open_order_token_ids:
                print(f"   ⏭️  Skipping {market.get('question')[:20]}... (Active Order Exists)")
                continue
            question = market.get("question", "")
            yes_price = market.get("yes_price", 0.5)
            no_price = market.get("no_price", 0.5)
            
            # FILTER 1: Must have a clear favorite (>55% implied)
            if yes_price < 0.55 and no_price < 0.55:
                continue  # Too close to 50/50
            
            # Determine which side is favorite
            if yes_price >= no_price:
                favorite_side = "YES"
                favorite_price = yes_price
                token_id = market.get("yes_token")
            else:
                favorite_side = "NO"
                favorite_price = no_price
                token_id = market.get("no_token")
            
            # FILTER 2: Skip very high prices (>95c, low upside)
            if favorite_price > 0.95:
                continue
            
            print(f"\n   🔎 Analyzing: {question[:60]}...")
            print(f"      Market: {favorite_side} @ ${favorite_price:.2f}")
            
            # 3. LLM Validation (Perplexity/Gemini)
            try:
                is_valid, reason, conf = self.validator.validate(
                    market_question=question,
                    outcome=favorite_side,
                    price=favorite_price,
                    additional_context=RISK_MANAGER_PROMPT,
                    fast_mode=False # 🧠 RESTORE THE BRAIN (Full Analysis)
                )
            except Exception as e:
                print(f"      ⚠️ Validator Error: {e}")
                continue
            
            if is_valid and conf >= self.min_conf:
                print(f"      ✅ GREEN LIGHT: {reason} (conf: {conf*100:.0f}%)")
                
                # Calculate bet size
                bet_size = min(5.0, min(self.max_bet, max(self.min_bet, self.balance * self.bet_pct))) # HARD CAP $5
                if self.balance < self.min_bet:
                    print(f"      💸 Insufficient balance: ${self.balance:.2f}")
                    continue
                
                # Execute trade
                self.execute_bet(market, favorite_side, size=bet_size, price=favorite_price + 0.01)
                trades_this_scan += 1
                break  # Exit after successful trade attempt
            else:
                print(f"      🛑 PASS: {reason} (conf: {conf*100:.0f}%)")
                
                # Log PASS activity for visibility
                if self.context and self.LLMActivity:
                    import uuid
                    try:
                        self.context.log_llm_activity(self.LLMActivity(
                            id=str(uuid.uuid4())[:8],
                            agent=self.AGENT_NAME,
                            timestamp=datetime.datetime.now().isoformat(),
                            action_type="validate",
                            market_question=question[:100],
                            prompt_summary="Fast Mode Validation",
                            reasoning=reason,
                            conclusion="PASS",
                            confidence=conf,
                            data_sources=["Gamma API", "Pattern Match"],
                            duration_ms=0
                        ))
                    except Exception as e:
                        print(f"      ⚠️ Failed to log PASS activity: {e}")

            # Log BET activity (Green Light)
            if is_valid and conf >= self.min_conf and self.context and self.LLMActivity:
                import uuid
                try:
                    self.context.log_llm_activity(self.LLMActivity(
                        id=str(uuid.uuid4())[:8],
                        agent=self.AGENT_NAME,
                        timestamp=datetime.datetime.now().isoformat(),
                        action_type="validate",
                        market_question=question[:100],
                        prompt_summary="Fast Mode Validation",
                        reasoning=reason,
                        conclusion="BET",
                        confidence=conf,
                        data_sources=["Gamma API", "Pattern Match"],
                        duration_ms=0
                    ))
                except Exception as e:
                    print(f"      ⚠️ Failed to log BET activity: {e}")


    def save_state(self):
        """Save state to json."""
        try:
            state = {
                "sports_trader_last_activity": f"Trades: {self.trades_made}",
                "timestamp": datetime.datetime.now().isoformat()
            }
            # Don't write mode to state file - let dashboard determine from global dry_run
            for path in self._state_file_paths():
                try:
                    with open(path, "w") as f:
                        json.dump(state, f)
                except Exception:
                    continue
        except: pass

    def run(self):
        print("🤖 SPORTS TRADER STARTED - Direct Polymarket Mode")
        while True:
            # 0. Sync State with Supabase
            if HAS_SUPABASE:
                try: 
                    supa = get_supabase_state()
                    if supa and not getattr(supa, "use_local_fallback", False):
                        if not supa.is_agent_running("sport"):
                            print("Paused via Supabase.")
                            time.sleep(60)
                            continue
                except Exception as e:
                    print(f"⚠️ Supabase check failed: {e}. Falling back to local state.")

            if not self._is_locally_running():
                print("Paused via local state file.")
                time.sleep(60)
                continue
            
            # Check Config
            current_config = load_config("sports_trader")
            if not current_config.get("active", True):
                 print("Paused via Config. Sleeping...")
                 time.sleep(60)
                 continue

            # 1. Auto-Redeem winning positions
            if self.redeemer:
                try: self.redeemer.scan_and_redeem()
                except: pass
            
            # 2. Refresh balance
            try:
                self.balance = self.pm.get_usdc_balance()
            except: pass
            
            # 2.5 HEARTBEAT LOG - proves agent is alive and Supabase works
            if self.context and self.LLMActivity:
                try:
                    import uuid
                    self.context.log_llm_activity(self.LLMActivity(
                        id=str(uuid.uuid4())[:8],
                        agent=self.AGENT_NAME,
                        timestamp=datetime.datetime.now().isoformat(),
                        action_type="heartbeat",
                        market_question=f"Scanning sports markets...",
                        prompt_summary="Heartbeat - Agent Active",
                        reasoning=f"Balance: ${self.balance:.2f}, Mode: {'LIVE' if not self.dry_run else 'DRY RUN'}",
                        conclusion="SCANNING",
                        confidence=1.0,
                        data_sources=["Gamma API", "Polymarket"],
                        duration_ms=0
                    ))
                    print(f"  🟢 Heartbeat logged to Supabase")
                except Exception as e:
                    print(f"  ⚠️ Heartbeat failed: {e}")
            
            # 3. Scan live markets directly from Polymarket
            try:
                self.scan_live_markets()
            except Exception as e:
                print(f"Error scanning markets: {e}")
            
            self.save_state()
            
            # 4. Self-Learning Cycle
            self.run_learning_cycle()

            self.save_state()
            print(f"\n⏳ Next scan in {self.scan_interval}s...")
            time.sleep(self.scan_interval)

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    bot = SportsTrader(dry_run=not is_live)
    bot.run()
