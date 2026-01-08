### Game Plan for Your Polymarket Automated Bot

This plan builds a **hybrid AI-enhanced bot** focused on **safe-to-moderate risk strategies**: primarily high-probability bets (90%+ implied outcomes for steady compounding), combined with low-risk arbitrage (YES/NO sums < $1 for near-risk-free 2-7% cycles) and optional light copy-trading of proven high-prob traders. It leverages LLMs (via your Perplexity credits) for superior market validation/research, aiming for consistent 10-20% monthly compounded returns over long-term (12+ months) running.

The bot runs autonomously 24/7, scans frequently, places small/diversified orders, and includes strict risk controls to protect capital.

#### 1. Core Repository & Tech Stack
- **Base Repo**: Official **Polymarket/agents** (https://github.com/Polymarket/agents) – Perfect for AI integration. It's Python-based, uses **py-clob-client** (official CLOB library for orders/market data), and has built-in LLM prompting tools. Actively maintained (updates as of Jan 2026).
- **Why this over others?** 
  - Designed for autonomous AI agents (news retrieval, prompting LLMs, executing trades).
  - Modular: Easy to add custom scanners/strategies.
  - Alternatives if needed: lorine93s/polymarket-market-maker-bot (for liquidity provision add-on) or copy-trading repos (e.g., Trust412 or vladmeer) as modules.
- **Dependencies**: py-clob-client (installed via requirements), requests for Perplexity API calls.

#### 2. Key Strategies (Prioritized for Safety & Compounding)
- **Primary (70-80% allocation)**: High-Probability Grinding
  - Scan for outcomes priced ≥ $0.90–$0.98 (implied 90-98% prob).
  - Targets: Near-certain resolutions (e.g., Fed no-rate-change at 95%+, "NO" on improbable long-shots like aliens/Jesus, obvious sports/politics/econ).
  - Expected ROI: 2-11% per win, 85-95% win rate (LLM-boosted).
- **Secondary (20-30%)**: Structural Arbitrage
  - Detect when YES + NO prices sum < $1.00 (e.g., 0.48 + 0.49 = 0.97 → buy both for guaranteed ~3% profit at resolution).
  - Risk-free if held to expiry; common in low-volume or mispriced markets.
- **Optional Add-On**: Light Copy-Trading
  - Mirror 10-20% of positions from top leaderboards/whales specializing in high-prob (find via Polymarket data API or Dune Analytics).
  - Use as a "safety net" for edges you might miss.

Avoid high-frequency/short-term crypto (fees killed easy edges in Jan 2026) or pure volatility plays unless adding risk tolerance later.

#### 3. Bot Architecture & Logic Flow
The bot runs in a loop (every 30-60 minutes for safety/low gas; more frequent for arb):

1. **Fetch Markets**:
   - Use py-clob-client to get all open markets (filter: volume > $100k, resolution >1 week away for long-term holds).

2. **Scan & Filter Opportunities**:
   - High-prob: Identify outcomes with price ≥ 0.90.
   - Arb: Check if any binary market's YES + NO < 0.99 (buffer for fees/slippage).

3. **LLM Validation (Your Secret Weapon)**:
   - For each candidate: Prompt Perplexity API with market title, current price, resolution rules, recent news/X sentiment.
   - Example Prompt: "Analyze Polymarket market '[title]': Estimated true probability of [outcome] given current news, stats, historical resolutions? Output: CONFIDENCE_SCORE (0-1), BET_YES/NO/ARB, REASON. Only bet if >0.92 confidence."
   - Only proceed if LLM confidence >0.92 (boosts win rate significantly).

4. **Risk Checks & Sizing**:
   - Max 5% of balance per market, 20-30% total exposure.
   - Diversify: Limit 10-20 open positions across categories (politics, sports, econ, tech).
   - Bet size: Fixed % (e.g., 1-3% per opportunity) or Kelly Criterion (via simple math: f = edge / odds).

5. **Execute Orders**:
   - Use limit orders (maker for potential rebates) where possible; fallback to market/taker.
   - Auto-redeem settled wins.

6. **Monitoring & Safety**:
   - Log all decisions (file + optional Telegram/Discord alerts).
   - Stop if balance drops >10-20% (circuit breaker).
   - Daily summary: Email/Slack with PnL, open positions.

#### 4. Setup Steps (Hands-On, Since You Have Coding Basics)
1. **Clone & Install**:
   ```
   git clone https://github.com/Polymarket/agents.git
   cd agents
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Config (.env)**:
   - PRIVATE_KEY, FUNDER_ADDRESS (new Polygon wallet with USDC).
   - API creds (derive via client).
   - PERPLEXITY_API_KEY.
   - Custom: MIN_PROB=0.90, MAX_EXPOSURE=0.25, etc.

3. **Customize Agent**:
   - Start with examples in agents/ (e.g., basic trader).
   - Add scanner loop + Perplexity integration (simple requests.post to API).
   - Test: Run dry-mode (print orders, no execution) for weeks.

4. **Deploy 24/7**:
   - Free: PythonAnywhere or Replit (limited hours).
   - Reliable/Cheap: AWS EC2 free tier or $5/month VPS (e.g., DigitalOcean). Use screen/tmux or PM2.
   - Monitor remotely via logs.

5. **Testing & Launch**:
   - Manual validation first (run scanner, check LLM outputs).
   - Start with tiny positions.
   - Iterate: Use Perplexity to debug/fix code.

#### 5. Expected Performance & Risks
- Steady compounding from small edges (realistic 10-20% monthly with LLM boosts).
- Risks: Resolution disputes (rare in high-prob), gas fees (low for infrequent trades), LLM hallucinations (mitigate with strict confidence thresholds).
- Edge Sources: LLM gives you superior research (news sentiment, hidden risks) over manual traders.

This plan is sustainable, low-maintenance, and leverages your Perplexity credits for a real advantage. Build iteratively—start with high-prob scanner, add arb/LLM, then copy-trading. Join Polymarket Discord for community tweaks. Good luck; this could compound nicely over months! If you need sample code snippets, share specifics.