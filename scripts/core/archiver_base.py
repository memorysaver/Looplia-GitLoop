#!/usr/bin/env python3
"""
Base Archiver - Abstract base class for type-specific archivers.

Implements Template Method pattern - defines the archiving workflow,
delegates type-specific behavior to subclasses.
"""

import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from core.utils import get_logger, load_config, load_json, save_json

logger = get_logger(__name__)


class BaseArchiver(ABC):
    """Base class for type-specific archivers.

    Implements Template Method pattern - defines the archiving workflow,
    delegates type-specific behavior to subclasses.
    """

    def __init__(self, config_path: Path, subscriptions_base_dir: Path):
        """Initialize archiver with config and subscriptions directories.

        Args:
            config_path: Path to type-specific sources.json config
            subscriptions_base_dir: Base directory for subscriptions
        """
        self.config_path = config_path
        self.subscriptions_base_dir = subscriptions_base_dir
        self.config = self.load_config()
        if not self.config:
            raise ValueError(f"Failed to load config from {config_path}")

    @abstractmethod
    def get_handler_class(self):
        """Return the handler class for this archiver type.

        Returns:
            Class (not instance) of handler (e.g., YouTubeHandler)
        """
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type (youtube, podcast, blog, news)."""
        pass

    def load_config(self) -> Optional[dict]:
        """Load configuration file."""
        return load_config(self.config_path)

    def get_output_dir(self, source_key: str) -> Path:
        """Get output directory for a source."""
        return self.subscriptions_base_dir / self.source_type / source_key

    def get_archived_ids(self, source_key: str) -> Set[str]:
        """Load set of already archived entry IDs for a source."""
        output_dir = self.get_output_dir(source_key)
        index_path = output_dir / "index.json"
        if index_path.exists():
            index = load_json(index_path)
            if index:
                return set(index.get("archived_ids", []))
        return set()

    def update_index(self, source_key: str, new_entries: list, source_config: dict):
        """Update the index file for a source with new entries."""
        output_dir = self.get_output_dir(source_key)
        index_path = output_dir / "index.json"

        # Load or create index
        if index_path.exists():
            index = load_json(index_path) or {}
        else:
            index = {}

        if not index:
            index = {
                "source_key": source_key,
                "source_name": source_config["name"],
                "source_type": self.source_type,
                "source_url": source_config["url"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "archived_ids": [],
                "entries": [],
            }

        # Add new entries
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

    def process_source(self, source: dict, force_reprocess: bool = False) -> int:
        """Process a single source and return count of new entries.

        Template method - orchestrates the archiving workflow.
        """
        source_key = source["key"]
        logger.info(f"Processing source: {source['name']} ({source_key})")

        # Get handler instance
        handler_class = self.get_handler_class()
        handler = handler_class(source)

        # Create output directory
        output_dir = self.get_output_dir(source_key)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get already archived IDs
        archived_ids = set() if force_reprocess else self.get_archived_ids(source_key)

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
                # Enrich entry
                enriched = handler.enrich_entry(entry)
                if enriched is None:  # Skip filtered entries
                    continue
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
            self.update_index(source_key, new_entries, source)

        return len(new_entries)

    def run(self, source_key: Optional[str] = None, force_reprocess: bool = False):
        """Main entry point - process all enabled sources.

        Args:
            source_key: If provided, only process this specific source
            force_reprocess: If True, reprocess even archived entries
        """
        total_new = 0
        for source in self.config.get("sources", []):
            # Skip disabled sources
            if not source.get("enabled", True):
                logger.info(f"Skipping disabled source: {source['key']}")
                continue

            # If specific source requested, only process that one
            if source_key and source["key"] != source_key:
                continue

            new_count = self.process_source(source, force_reprocess)
            total_new += new_count

        logger.info(f"Archiving complete. Total new entries: {total_new}")
