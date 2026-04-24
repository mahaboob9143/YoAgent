"""
core/flags.py — Config reader for InstaAgent.

Reads config.yaml on every call.
"""

import os
from typing import Any, Dict

import yaml

CONFIG_PATH = "config.yaml"


def load_config(path: str = CONFIG_PATH) -> Dict[str, Any]:
    """Load and return the full config.yaml as a dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def get_config(path: str = CONFIG_PATH) -> Dict[str, Any]:
    """Return full config dict. Alias for load_config with error handling."""
    try:
        if not os.path.exists(path):
            return {}
        return load_config(path)
    except Exception:
        return {}
