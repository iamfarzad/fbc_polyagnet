# War Room Architecture: The "Hedge Fund Brain" Implementation Plan

> **Goal:** Transform the system from a collection of scripts into a unified "Hedge Fund" organism. The system will have **Eyes** (Smart Context), a **Brain** (Hedge Fund Analyst), and a **Command Center** (Dashboard War Room).

---

## Phase 1: The Sensory System (Backend) 👁️

**Objective:** Give the agents full context awareness (Wallet, History, Market Depth, Sentiment).

### 1.1 Master Config System
**File:** `agents/utils/config.py`
- **Purpose:** Single source of truth for agent behavior (Aggression, Risk, Mode).
- **Features:** Dynamic reloading without restart.
- **Schema:**
  ```json
  {
      "scalper": { "active": true, "mode": "high_freq", "max_spread": 0.01 },
      "copy_trader": { "active": true, "fade_whales": false, "whale_tier": "gold" },
      "research": { "active": true, "depth": "deep_dive" }
  }
  ```

### 1.2 Smart Context Engine
**File:** `agents/application/smart_context.py`
- **Purpose:** Aggregates data into a single "Context Payload" for the LLM.
- **Inputs:**
  - **Internal:** Wallet Balance, Daily PnL, Win/Loss Streak (from `full_ledger.md`).
  - **Market:** Order Book Depth (Bid/Ask pressure), Spread.
  - **External:** Global Sentiment (via optional News API).

---

## Phase 2: The Hedge Fund Brain (Backend) 🧠

**Objective:** Replace simple "If/Then" logic with nuanced LLM risk assessment.

### 2.1 Hedge Fund Analyst
**File:** `agents/application/hedge_fund_analyst.py`
- **Role:** Senior Risk Manager.
- **Input:** Context Payload + Proposed Trade.
- **Logic:**
  - **Streak Analysis:** "We lost 3 in a row, cut size by 50%."
  - **Liquidity Check:** "Order book too thin for $50 bet, reduce to $10."
  - **Sentiment Check:** "News contradicts this trade. Abort."
- **Output:** `Decision` (APPROVED/REJECTED), `RiskMethod` (Aggressive/Conservative), `SizeMultiplier`.

---

## Phase 3: The Research Division (New Agent) 🕵️

**Objective:** Proactive market analysis using the "New Agent Instructions" prompts.

### 3.1 Research Agent
**File:** `agents/application/research_agent.py`
- **Role:** The "Deep Dive" investigator.
- **Capabilities (Prompts):**
  - **Social Velocity:** "Compare mention frequency vs 30-day baseline."
  - **Cynical VC:** "Identify the weakest link in their ecosystem."
  - **Narrative Scout:** "Scan for narrative seeds in specific sectors."
  - **Whale Tracker:** "Trace digital footprints of Smart Money."
  - **Deception Audit:** "Verify LP locks and founder history."

---

## Phase 4: The War Room (Frontend) 🎮

**Objective:** A unified Command & Control dashboard.

### 4.1 Agent Control Panel
**File:** `dashboard-frontend/components/agent-config-panel.tsx`
- **UI:** Tabs for each agent (Scalper, Copy, Research).
- **Controls:**
  - **Sliders:** Bet Size, Confidence Threshold.
  - **Toggles:** Active/Paused, Fade Whales Mode.
  - **Input:** Command Line for specific instructions ("Scan BTC now").

### 4.2 War Room Display ("Brain Logs")
**File:** `dashboard-frontend/components/war-room.tsx`
- **Purpose:** See *why* the AI made a decision.
- **Visuals:**
  - **Live Thoughts:** Stream of `HedgeFundAnalyst` reasoning.
  - **Heartbeat:** "Last Action: 3s ago", "Next Scan: 27s".
  - **Focus:** "Currently Analyzing: T1 vs GenG".

### 4.3 Data Viz
- **Allocation Chart:** Pie chart of portfolio risk distribution.
- **Performance:** Bar chart of Win Rate per agent type.

---

## Phase 5: Integration & Execution 🔗

### 5.1 Update Existing Agents
- **Scalper (`pyml_scalper.py`)**: Inject `SmartContext` + `HedgeFundAnalyst`.
- **Copy Trader (`pyml_copy_trader.py`)**: Inject `SmartContext` + `HedgeFundAnalyst`.

### 5.2 Dashboard API
- **Endpoints:**
  - `GET /api/context`: View current "Sensory" state.
  - `POST /api/command`: Send orders to Swarm.
  - `GET /api/brain-logs`: Stream Analyst reasoning.

---

## Execution Checklist

1. **Build Backend Core:** `config.py`, `smart_context.py`, `hedge_fund_analyst.py`.
2. **Build Research Agent:** Implement the advanced prompts.
3. **Upgrade Dashboard:** Build `agent-config-panel.tsx` and `war-room.tsx`.
4. **Wire It Up:** Connect Dashboard Controls -> Config API -> Agent Logic.
