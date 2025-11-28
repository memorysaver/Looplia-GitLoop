#!/usr/bin/env python3
"""
Blog Handler - Uses feedparser for RSS/Atom feeds.
Extends BaseSubscriptionHandler for blog-specific behavior.
"""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

import feedparser

# Add parent directory to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base_handler import BaseSubscriptionHandler
from core.utils import get_logger, sanitize_id

logger = get_logger(__name__)


class BlogHandler(BaseSubscriptionHandler):
    """Handler for blog RSS/Atom feeds."""

    @property
    def source_type(self) -> str:
        """Return source type identifier."""
        return "blog"

    def fetch_entries(self, archived_ids: Set[str]) -> List[Dict]:
        """Fetch new entries from RSS feed."""
        feed = feedparser.parse(self.url)

        if feed.bozo and feed.bozo_exception:
            logger.warning(f"Feed parsing warning: {feed.bozo_exception}")

        entries = []
        for item in feed.entries:
            entry_id = self._get_entry_id(item)

            if entry_id not in archived_ids:
                entries.append(
                    {
                        "id": entry_id,
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "published": self._get_published_date(item),
                        "author": item.get("author"),
                        "summary": item.get("summary"),
                        "_raw": item,  # Keep raw data for enrichment
                    }
                )

        return entries

    def _get_entry_id(self, item: Dict) -> str:
        """Generate a unique ID for the entry."""
        # Prefer GUID if available
        if item.get("id"):
            return sanitize_id(item["id"])

        # Fallback to link hash
        if item.get("link"):
            return hashlib.md5(item["link"].encode()).hexdigest()[:16]

        # Last resort: title hash
        return hashlib.md5(item.get("title", "").encode()).hexdigest()[:16]

    def _get_published_date(self, item: Dict) -> Optional[str]:
        """Extract and normalize published date."""
        if item.get("published_parsed"):
            try:
                dt = datetime(*item["published_parsed"][:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        if item.get("updated_parsed"):
            try:
                dt = datetime(*item["updated_parsed"][:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        return item.get("published") or item.get("updated")

    def enrich_entry(self, entry: Dict) -> Optional[Dict]:
        """Enrich entry with blog-specific metadata."""
        raw = entry.pop("_raw", {})

        enriched = {
            "id": entry["id"],
            "source_type": self.source_type,
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published"),
            "author": entry.get("author"),
        }

        enriched.update(self._enrich_blog(raw))
        return enriched

    def _enrich_blog(self, raw: Dict) -> Dict:
        """Extract blog-specific metadata."""
        data = {
            "summary": raw.get("summary"),
            "content": self._get_content(raw),
        }

        # Tags/categories
        tags = [tag.get("term") for tag in raw.get("tags", []) if tag.get("term")]
        if tags:
            data["tags"] = tags

        # Media/thumbnails
        if hasattr(raw, "media_thumbnail") and raw.media_thumbnail:
            data["thumbnail"] = raw.media_thumbnail[0].get("url")

        return data

    def _get_content(self, raw: Dict) -> Optional[str]:
        """Extract main content from entry."""
        # Prefer full content over summary
        if raw.get("content"):
            for content in raw["content"]:
                if content.get("type") in ("text/html", "text/plain"):
                    return content.get("value")

        return raw.get("summary")
