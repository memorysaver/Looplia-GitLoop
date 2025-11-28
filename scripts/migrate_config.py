#!/usr/bin/env python3
"""
Migration script to convert v2.0.0 single config to v3.0.0 type-specific configs.

Splits config/sources.json by subscription type into separate config files.
"""

import json
import sys
from pathlib import Path

# Add scripts to path for imports
BASE_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from core.utils import get_logger, load_json, save_json

logger = get_logger(__name__)

CONFIG_V2_PATH = BASE_DIR / "config" / "sources.json"
CONFIG_V3_DIR = BASE_DIR / "config"

# Type folder mapping
TYPE_FOLDER_MAP = {
    "youtube": "youtube",
    "youtube_channel": "youtube",
    "youtube_playlist": "youtube",
    "podcast": "podcast",
    "blogs": "blog",
    "blog": "blog",
    "news": "news",
}

# Type metadata
TYPE_METADATA = {
    "youtube": {
        "description": "YouTube channel subscriptions",
        "requires_cookies": True,
        "requires_ytdlp": True,
        "runner": "self-hosted",
    },
    "podcast": {
        "description": "Podcast RSS feed subscriptions",
        "requires_cookies": False,
        "requires_ytdlp": False,
        "runner": "ubuntu-latest",
    },
    "blog": {
        "description": "Blog RSS feed subscriptions",
        "requires_cookies": False,
        "requires_ytdlp": False,
        "runner": "ubuntu-latest",
    },
    "news": {
        "description": "News aggregator subscriptions",
        "requires_cookies": False,
        "requires_ytdlp": False,
        "runner": "ubuntu-latest",
    },
}


def migrate_config():
    """Migrate v2.0.0 config to v3.0.0 type-specific configs."""
    logger.info("Starting config migration from v2.0.0 to v3.0.0")

    # Load old config
    old_config = load_json(CONFIG_V2_PATH)
    if not old_config:
        logger.error(f"Failed to load old config from {CONFIG_V2_PATH}")
        return False

    logger.info(f"Loaded old config with {len(old_config.get('sources', []))} sources")

    # Group sources by type
    by_type = {"youtube": [], "podcast": [], "blog": [], "news": []}

    for source in old_config.get("sources", []):
        source_type = source.get("type", "").lower()

        # Map old type names to new type names
        normalized_type = TYPE_FOLDER_MAP.get(source_type)
        if not normalized_type:
            logger.warning(f"Unknown source type '{source_type}' for {source.get('key')}, skipping")
            continue

        by_type[normalized_type].append(source)
        logger.info(f"Mapped {source.get('key')} ({source_type}) -> {normalized_type}")

    # Create type-specific configs
    created_count = 0
    for source_type, sources in by_type.items():
        if not sources:
            logger.info(f"No sources for type '{source_type}', skipping")
            continue

        config_dir = CONFIG_V3_DIR / source_type
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "sources.json"

        # Build new config
        new_config = {
            "version": "3.0.0",
            "type": source_type,
            "metadata": TYPE_METADATA.get(source_type, {}),
            "sources": sources,
        }

        # Save config
        if save_json(config_path, new_config):
            logger.info(f"Created {config_path} with {len(sources)} sources")
            created_count += 1
        else:
            logger.error(f"Failed to save {config_path}")

    logger.info(f"Migration complete. Created {created_count} type-specific config files")
    return True


def main():
    """Main entry point."""
    try:
        if migrate_config():
            logger.info("✓ Migration successful")
            return 0
        else:
            logger.error("✗ Migration failed")
            return 1
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
