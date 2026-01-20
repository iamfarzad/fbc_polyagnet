#!/usr/bin/env python3
"""
Polymarket Bot Dashboard API Server

This file delegates to the main API implementation in agents/api.py
All endpoints are defined there for better code organization.

DEPLOYMENT: On Fly.io, the fly.toml configuration points to agents.api:app
LOCAL DEV: Run with: python -m uvicorn agents.api:app --reload --port 8000
"""

import sys
import os

# Ensure agents package is resolvable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import and expose the main FastAPI app
from agents.api import app

if __name__ == "__main__":
    import uvicorn
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the server
    # Note: In production (Fly.io), this file is not used - fly.toml points directly to agents.api:app
    uvicorn.run(
        "agents.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable hot reload for development
        log_level="info"
    )
