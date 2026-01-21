import json
import os
import logging

# Define paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # agents/
CONFIG_FILE = os.path.join(BASE_DIR, "dynamic_config.json")

logger = logging.getLogger("Config")

# --- THE MASTER SCHEMA ---
DEFAULT_CONFIG = {
    "global_dry_run": True,
    
    "esports": {
        "active": False,
        "mode": "aggressive",  # safe, aggressive, degen
        "max_size": 20.0,
        "min_edge": 0.02,
        "use_llm": True
    },
    "scalper": {
        "active": True,
        "mode": "high_freq",   # high_freq, sniper
        "max_size": 500.00,      # Default conservative
        "min_spread": 0.01,
        "use_llm_sentiment": False
    },
    "copy_trader": {
        "active": False,
        "whale_tier": "gold",  # gold (trusted), silver (all)
        "max_copy_amount": 5.0,
        "fade_whales": False   # If True, bet AGAINST the whale
    },
    "smart_politics": {
        "active": False,
        "max_size": 10.0,
        "min_confidence": 0.75
    },
    "sports_trader": {
        "active": False,
        "leagues": ["NFL", "NBA", "MLB"],
        "max_size": 10.0,
        "min_edge": 0.03
    },
    "safe_trader": {
        "active": False,
        "max_size": 5.0,
        "min_edge_pct": 15.0
    }
}

def load_config(agent_name=None):
    """
    Loads config from dynamic_config.json.
    If agent_name is provided, returns just that section.
    """
    data = DEFAULT_CONFIG.copy()
    
    # Try to load existing
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                # Deep merge defaults (simple version)
                for k, v in saved.items():
                    if isinstance(v, dict) and k in data:
                        data[k].update(v)
                    else:
                        data[k] = v
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
    else:
        # Create if missing
        save_config(DEFAULT_CONFIG)

    if agent_name:
        return data.get(agent_name, data.get(agent_name.replace("_trader", ""), {}))
    
    return data

def save_config(new_full_config):
    """Saves the full configuration object to disk."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(new_full_config, f, indent=4)
        return new_full_config
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return new_full_config

def update_section(agent_name, updates):
    """Updates a specific section of the config."""
    current = load_config()
    if agent_name in current:
        current[agent_name].update(updates)
    else:
        current[agent_name] = updates
    return save_config(current)
