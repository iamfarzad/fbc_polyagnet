# Source of Truth: Polyagent Architecture

## Active Agents (Production)

| Agent | File | Entry Point | Purpose |
|-------|------|-------------|---------|
| **SafeAgent** | `application/pyml_trader.py` | `fly.toml: safe` | High-probability market bets |
| **ScalperAgent** | `application/pyml_scalper.py` | `fly.toml: scalper` | 15-min crypto scalping |
| **CopyTrader** | `application/pyml_copy_trader.py` | `fly.toml: copy` | Follow whale trades |
| **SmartAgent** | `application/smart_trader.py` | `fly.toml: smart` | Politics/general markets |
| **SportsAgent** | `application/sports_trader.py` | `fly.toml: sports` | Sports betting |
| **EsportsAgent** | `application/esports_trader.py` | `fly.toml: esports` | eSports betting |

## Core Infrastructure

| Component | File | Purpose |
|-----------|------|---------|
| **API Server** | `api.py` | Dashboard REST/WS API |
| **Orchestrator** | `main.py` | Multi-agent process manager |
| **Chat Agent** | `fbp_agent.py` | AI assistant for dashboard |

## Utilities

| Utility | File | Purpose |
|---------|------|---------|
| **Shared Context** | `utils/context.py` | Multi-agent state coordination |
| **Supabase Client** | `utils/supabase_client.py` | Cloud state management |
| **Auto Redeemer** | `utils/auto_redeem.py` | Settlement sniping |
| **Risk Engine** | `utils/risk_engine.py` | Drawdown/exposure checks |
| **Validator** | `utils/validator.py` | 3-tier LLM validation |

## Polymarket Integration

| Component | File | Purpose |
|-----------|------|---------|
| **Main Client** | `polymarket/polymarket.py` | CLOB API wrapper |
| **Market Discovery** | `polymarket/gamma.py` | Gamma API for markets |

## Data Flow

```
Dashboard (Vercel) <---> API (Fly.io) <---> Supabase (Cloud DB)
                                   |
                                   v
                        +------------------+
                        |  Agent Machines  |
                        |  (6 processes)   |
                        +------------------+
                                   |
                                   v
                           Polymarket CLOB
```

## Configuration

- **Deployment:** `fly.toml` defines all processes
- **Secrets:** `fly secrets` (POLYGON_WALLET_PRIVATE_KEY, SUPABASE_*, etc.)
- **Local:** `.env` file (NOT committed)
