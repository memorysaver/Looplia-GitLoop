#!/usr/bin/env python3
"""
Main RSS Archiver Script
Orchestrates fetching and archiving RSS entries from configured sources.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from feed_handler import FeedHandler
from utils import get_logger, load_config, load_json, save_json
from youtube_handler import YouTubeHandler

logger = get_logger(__name__)

# Base paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "sources.json"
RSS_DIR = BASE_DIR / "rss"


def get_handler(source_type: str):
    """Return appropriate handler based on source type."""
    handlers = {
        "youtube_channel": YouTubeHandler,
        "youtube_playlist": YouTubeHandler,
        "podcast": FeedHandler,
        "blog": FeedHandler,
    }
    return handlers.get(source_type)


def get_archived_ids(source_key: str) -> set:
    """Load set of already archived entry IDs for a source."""
    index_path = RSS_DIR / source_key / "index.json"
    if index_path.exists():
        index = load_json(index_path)
        if index:
            return set(index.get("archived_ids", []))
    return set()


def update_index(source_key: str, new_entries: list, source_config: dict):
    """Update the index file for a source with new entries."""
    index_path = RSS_DIR / source_key / "index.json"

    if index_path.exists():
        index = load_json(index_path)
        if not index:
            index = {}
    else:
        index = {}

    if not index:
        index = {
            "source_key": source_key,
            "source_name": source_config["name"],
            "source_type": source_config["type"],
            "source_url": source_config["url"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "archived_ids": [],
            "entries": [],
        }

    # Add new entries to index
    for entry in new_entries:
        if entry["id"] not in index["archived_ids"]:
            index["archived_ids"].append(entry["id"])
            index["entries"].append(
                {
                    "id": entry["id"],
                    "title": entry.get("title", "Untitled"),
                    "published": entry.get("published"),
                    "archived_at": entry.get("archived_at"),
                    "file": f"{entry['id']}.json",
                }
            )

    index["last_updated"] = datetime.now(timezone.utc).isoformat()
    index["total_entries"] = len(index["archived_ids"])

    save_json(index_path, index)


def process_source(source: dict, force_reprocess: bool = False) -> int:
    """Process a single source and return count of new entries."""
    source_key = source["key"]
    source_type = source["type"]

    logger.info(f"Processing source: {source['name']} ({source_key})")

    # Get appropriate handler
    handler_class = get_handler(source_type)
    if not handler_class:
        logger.error(f"Unknown source type: {source_type}")
        return 0

    handler = handler_class(source)

    # Create output directory
    output_dir = RSS_DIR / source_key
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get already archived IDs
    archived_ids = set() if force_reprocess else get_archived_ids(source_key)

    # Fetch new entries
    try:
        entries = handler.fetch_entries(archived_ids)
    except Exception as e:
        logger.error(f"Failed to fetch entries for {source_key}: {e}")
        return 0

    if not entries:
        logger.info(f"No new entries for {source_key}")
        return 0

    # Process and save each entry
    new_entries = []
    max_entries = source.get("options", {}).get("max_entries_per_run", 10)

    for entry in entries[:max_entries]:
        try:
            # Enrich entry with additional data (transcripts, etc.)
            enriched = handler.enrich_entry(entry)
            enriched["archived_at"] = datetime.now(timezone.utc).isoformat()

            # Save entry to file
            entry_path = output_dir / f"{enriched['id']}.json"
            save_json(entry_path, enriched)
            new_entries.append(enriched)

            logger.info(f"Archived: {enriched.get('title', enriched['id'])}")

        except Exception as e:
            logger.error(f"Failed to process entry {entry.get('id')}: {e}")
            continue

    # Update index
    if new_entries:
        update_index(source_key, new_entries, source)

    return len(new_entries)


def main():
    """Main entry point."""
    # Load configuration
    config = load_config(CONFIG_PATH)
    if not config:
        logger.error("Failed to load configuration")
        sys.exit(1)

    # Check for specific source or force reprocess from environment
    target_source = os.environ.get("SOURCE_KEY", "").strip()
    force_reprocess = os.environ.get("FORCE_REPROCESS", "false").lower() == "true"

    # Process sources
    total_new = 0
    for source in config.get("sources", []):
        # Skip disabled sources
        if not source.get("enabled", True):
            logger.info(f"Skipping disabled source: {source['key']}")
            continue

        # If specific source requested, only process that one
        if target_source and source["key"] != target_source:
            continue

        new_count = process_source(source, force_reprocess)
        total_new += new_count

    logger.info(f"Archiving complete. Total new entries: {total_new}")


if __name__ == "__main__":
    main()
