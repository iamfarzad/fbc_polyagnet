# Farzad Bayat Polymarket Bot

A sophisticated autonomous trading bot for Polymarket, featuring a dual-architecture system with a Python/FastAPI backend and a Next.js/React dashboard.

## 🚀 Features

### AI Trading Agents
The system runs three distinct autonomous agents:
1.  **Scalper Agent** (`pyml_ws_scalper.py`): High-frequency looking for arbitrage and scalping opportunities.
2.  **Safe Agent** (`pyml_trader.py`): Risk-managed agent focusing on high-probability setups with strict Kelly criteria.
3.  **Copy Trader** (`pyml_copy_trader.py`): Mimics trades from a curated list of high-performance wallets.

### Dashboard & Control
-   **Live Visualization**: Real-time display of PnL, Open Positions, Trade History, and Agent Status.
-   **Dynamic Configuration**:
    -   **Max Bet Control**: Adjust the maximum bet size for all agents directly from the UI (persisted to backend).
    -   **Dry Run Toggle**: Switch between "Simulation" and "Real Money" modes instantly.
    -   **Emergency Stop**: Halt all trading activities with a single click.

### Architecture
-   **Backend**: Python FastAPI service deployed on **Fly.io**. Handles market data, agent logic, and trade execution.
-   **Frontend**: Next.js (React/TypeScript) dashboard deployed on **Vercel**. Connects to the backend via API.

## 🛠 Technology Stack

-   **Backend**: Python 3.9, FastAPI, Uvicorn, Polymarket SDK (`py-clob-client`).
-   **Frontend**: Next.js 14, Tailwind CSS, Lucide Icons, Shadcn UI.
-   **Deployment**: Fly.io (Backend), Vercel (Frontend).

## 🏃‍♂️ Getting Started

### Prerequisites
-   Python 3.9+
-   Node.js 18+
-   Polymarket API Keys & Wallet Private Key

### Local Development

#### 1. Backend
```bash
cd agents
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your keys
# Run the API
python3 -m uvicorn api:app --reload
```

#### 2. Frontend
```bash
cd dashboard-frontend
npm install
npm run dev
```

## 🚢 Deployment

### Backend (Fly.io)
The backend is containerized and deployed to Fly.io.
```bash
cd agents
fly deploy
```

### Frontend (Vercel)
The frontend is deployed to Vercel and automatically builds on git push.
```bash
git push origin main
```

## ⚙️ Configuration
Key settings are managed via `agents/.env` and dynamic runtime state `agents/bot_state.json`.

-   `MAX_BET_USD`: Default maximum bet size (can be overridden via Dashboard).
-   `POLYGON_WALLET_PRIVATE_KEY`: Private key for the bot's specialized wallet.

## 📜 License
MIT
