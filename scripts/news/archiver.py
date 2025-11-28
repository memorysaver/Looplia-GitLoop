#!/usr/bin/env python3
"""
News-specific archiver script.
Orchestrates archiving of News subscriptions.
"""

import os
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.archiver_base import BaseArchiver
from news.handler import NewsHandler


class NewsArchiver(BaseArchiver):
    """News-specific archiver."""

    @property
    def source_type(self) -> str:
        """Return source type."""
        return "news"

    def get_handler_class(self):
        """Return the handler class for News."""
        return NewsHandler


if __name__ == "__main__":
    # Set up paths
    BASE_DIR = Path(__file__).parent.parent.parent
    config_path = BASE_DIR / "config" / "news" / "sources.json"
    subscriptions_dir = BASE_DIR / "subscriptions"

    # Create archiver
    archiver = NewsArchiver(config_path, subscriptions_dir)

    # Get environment variables (from workflow)
    source_key = os.environ.get("SOURCE_KEY", "").strip() or None
    force_reprocess = os.environ.get("FORCE_REPROCESS", "false").lower() == "true"

    # Run archiver
    archiver.run(source_key=source_key, force_reprocess=force_reprocess)
