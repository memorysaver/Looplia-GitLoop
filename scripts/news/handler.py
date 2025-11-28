#!/usr/bin/env python3
"""
News Handler - Uses feedparser for RSS/Atom feeds with news-specific enrichment.
Extends BaseSubscriptionHandler for news aggregator-specific behavior (e.g., HackerNews).
"""

import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

import feedparser

# Add parent directory to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base_handler import BaseSubscriptionHandler
from core.utils import get_logger, sanitize_id

logger = get_logger(__name__)


class NewsHandler(BaseSubscriptionHandler):
    """Handler for news aggregator RSS/Atom feeds."""

    @property
    def source_type(self) -> str:
        """Return source type identifier."""
        return "news"

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
        """Enrich entry with news-specific metadata."""
        raw = entry.pop("_raw", {})

        enriched = {
            "id": entry["id"],
            "source_type": self.source_type,
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published"),
            "author": entry.get("author"),
        }

        enriched.update(self._enrich_news(raw, entry))
        return enriched

    def _enrich_news(self, raw: Dict, entry: Dict) -> Dict:
        """Extract news aggregator-specific metadata (HackerNews, etc.)."""
        data = {
            "summary": raw.get("summary"),
        }

        # Extract domain from link
        link = entry.get("link", "")
        if link:
            try:
                parsed = urlparse(link)
                data["domain"] = parsed.netloc.replace("www.", "")
            except Exception:
                pass

        # Try to extract HackerNews-specific fields
        # HN RSS includes comments link in the description
        description = raw.get("summary", "") or ""

        # Look for "Comments" link which contains HN discussion URL
        comments_match = re.search(
            r'<a href="(https://news\.ycombinator\.com/item\?id=\d+)"[^>]*>Comments</a>',
            description,
        )
        if comments_match:
            data["comments_url"] = comments_match.group(1)
            # Extract item ID
            item_id_match = re.search(r"id=(\d+)", comments_match.group(1))
            if item_id_match:
                data["hn_id"] = item_id_match.group(1)

        # Try to extract points/score if present
        points_match = re.search(r"(\d+)\s*points?", description, re.IGNORECASE)
        if points_match:
            data["points"] = int(points_match.group(1))

        # Try to extract comment count if present
        comments_count_match = re.search(
            r"(\d+)\s*comments?", description, re.IGNORECASE
        )
        if comments_count_match:
            data["comments_count"] = int(comments_count_match.group(1))

        # Tags/categories
        tags = [tag.get("term") for tag in raw.get("tags", []) if tag.get("term")]
        if tags:
            data["tags"] = tags

        return data
