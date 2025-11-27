#!/usr/bin/env python3
"""
Utility functions for RSS Archiver.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional


def get_logger(name: str) -> logging.Logger:
    """Get configured logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(name)


def load_config(path: Path) -> Optional[dict]:
    """Load JSON configuration file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config from {path}: {e}")
        return None


def load_json(path: Path) -> Optional[dict]:
    """Load JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON from {path}: {e}")
        return None


def save_json(path: Path, data: Any, indent: int = 2) -> bool:
    """Save data to JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False, default=str)
        return True
    except Exception as e:
        logging.error(f"Failed to save JSON to {path}: {e}")
        return False


def sanitize_id(raw_id: str) -> str:
    """
    Sanitize an ID to be filesystem-safe.
    Keeps alphanumeric, hyphens, underscores.
    """
    # Remove URL prefixes
    if raw_id.startswith("http"):
        # Extract last path segment or query param
        raw_id = raw_id.split("/")[-1].split("?")[0]

    # Remove special characters, keep alphanumeric and some safe chars
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_id)

    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Trim and limit length
    return sanitized.strip("_")[:64]
