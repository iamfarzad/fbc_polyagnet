Based on the production-ready code in your `agents/application/` directory, here is the breakdown of the **Full Lifecycle** run for each agent.

### **1. Scalper Agent (`pyml_scalper.py`)**

* **Discovery**: Automatically generates slugs for the next available 15-minute crypto windows (e.g., `btc-updown-15m-{timestamp}`).
* **Signal Sync**: Connects to the Binance WebSocket for real-time price momentum on BTC, ETH, SOL, and XRP.
* **Entry**: Executes a "Smart Maker" (Queue Jumper) order. It joins small walls or jumps big ones to ensure fill priority.
* **Monitoring**: Uses dynamic timeouts (3s if volatile, 15s if calm) to manage stale orders.
* **Exit**: Employs a hybrid strategy: first attempts a Maker exit for profit; if PnL drops below -2.0%, it triggers a panic Taker exit.
* **Settlement**: Calls `AutoRedeemer` to pull USDC back to the Proxy Wallet upon market resolution.

### **2. Safe Agent (`pyml_trader.py`)**

* **Discovery**: Scans for high-volume markets with extreme probabilities (>85%).
* **Validation**: Uses an LLM (Perplexity/GPT) to confirm the consensus likelihood matches the market odds.
* **Entry**: Calculates position size using the **Kelly Criterion** and places a "Sniper" limit order 1 cent below market price.
* **Monitoring**: Tracks drawdown and scans for emergency exit conditions (e.g., a 30% drop from entry).
* **Exit**: Primarily holds to resolution for maximum payout.
* **Redemption**: winning funds are automatically redeemed via the Gnosis Safe Proxy.

### **3. Copy Trader Agent (`pyml_copy_trader.py`)**

* **Discovery**: Uses LLM research or a static whale list to identify top-performing addresses on Polymarket.
* **Signal**: Monitors these whales and filters for positions opened within the last 2 hours.
* **Entry**: Executes an aggressive limit order ($0.999) to clone the whale's trade instantly.
* **Monitoring**: Positions are logged in `copy_state.json` and tracked via the shared context.
* **Exit**: Mimics the whale's holding pattern, typically holding to resolution.
* **Redemption**: Settlement is handled through the integrated `AutoRedeemer`.

### **4. Smart Trader Agent (`smart_trader.py`)**

* **Discovery**: Fetches active markets in fee-free categories (politics, news, pop culture).
* **Analysis**: Conducts deep-dive research via Perplexity API search to find "true" probabilities.
* **Entry**: Places a bet only if there is a massive edge (>15%) and high LLM confidence (>90%).
* **Monitoring**: Periodically re-scans the news to update its research thesis.
* **Exit**: Strictly holds until resolution to avoid double transaction fees.
* **Redemption**: Funds are pulled back to the Gnosis Safe balance upon settlement.

### **5. Sports Trader Agent (`sports_trader.py`)**

* **Discovery**: Directly queries the Gamma API for live game-specific events (NBA, NFL, Soccer).
* **Analysis**: Acts as a "Contrarian Risk Manager," searching for injuries or schedule fatigue to find reasons *not* to bet on the favorite.
* **Entry**: Executes a market order on clear favorites (>55%) when the "Green Light" is given.
* **Monitoring**: Hold-to-resolution strategy.
* **Exit/Redemption**: Auto-redemption cycle clears positions once the game result is finalized on-chain.

### **6. Esports Trader Agent (`esports_trader.py`)**

* **Discovery**: Scans for 900+ potential esports markets using specific series IDs (LoL, CS2, Dota2).
* **Signal**: Exploits the ~30s stream delay by comparing real-time game data (Riot/PandaScore API) against stale Polymarket odds.
* **Entry**: Calculates win probability from live gold leads or kill counts and enters when an edge is detected.
* **Monitoring**: Polls game state every 8s during live matches to detect shifts.
* **Exit**: Exits when the market catches up to the real game state or the match concludes.

### **7. Lifecycle Utility: Exit Monitor (`exit_monitor.py`)**

* **Scan**: Continuously scans all open positions across every agent (except Copy Trader).
* **Re-Validation**: Re-runs a strict risk-management LLM check.
* **Liquidation**: If the thesis degrades or confidence drops below 40%, it immediately triggers a market sell to preserve capital.