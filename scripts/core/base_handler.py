#!/usr/bin/env python3
"""
Base Handler - Abstract base class for all subscription handlers.

Defines the contract that all handlers must implement.
Uses Strategy Pattern - each handler encapsulates its fetching/enrichment strategy.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set


class BaseSubscriptionHandler(ABC):
    """Abstract base class for all subscription handlers.

    Defines the contract that all handlers must implement.
    Uses Strategy Pattern - each handler encapsulates its fetching/enrichment strategy.
    """

    def __init__(self, source_config: Dict):
        """Initialize handler with source configuration.

        Args:
            source_config: Dict containing key, name, url, options, etc.
        """
        self.config = source_config
        self.options = source_config.get("options", {})
        self.url = source_config["url"]
        self.source_key = source_config["key"]
        self.source_name = source_config["name"]

    @abstractmethod
    def fetch_entries(self, archived_ids: Set[str]) -> List[Dict]:
        """Fetch new entries from the subscription source.

        Args:
            archived_ids: Set of already-archived entry IDs to skip

        Returns:
            List of entry dicts with at minimum: id, title, link, published
        """
        pass

    @abstractmethod
    def enrich_entry(self, entry: Dict) -> Optional[Dict]:
        """Enrich entry with additional metadata.

        Args:
            entry: Basic entry dict from fetch_entries()

        Returns:
            Enriched entry dict, or None to skip this entry
        """
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (youtube, podcast, etc.)."""
        pass

    def validate_config(self) -> bool:
        """Validate source configuration has required fields."""
        required = ["key", "name", "url"]
        return all(field in self.config for field in required)
