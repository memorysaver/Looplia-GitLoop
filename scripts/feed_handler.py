#!/usr/bin/env python3
"""
Generic Feed Handler - Uses feedparser for RSS/Atom feeds.
For blogs and news aggregators.
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import feedparser

from utils import get_logger, sanitize_id

logger = get_logger(__name__)


class FeedHandler:
    """Handler for generic RSS/Atom feeds (blogs, news aggregators)."""

    def __init__(self, source_config: dict):
        self.config = source_config
        self.options = source_config.get("options", {})
        self.url = source_config["url"]
        self.source_type = source_config["type"]

    def fetch_entries(self, archived_ids: set) -> list:
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

    def _get_entry_id(self, item: dict) -> str:
        """Generate a unique ID for the entry."""
        # Prefer GUID if available
        if item.get("id"):
            return sanitize_id(item["id"])

        # Fallback to link hash
        if item.get("link"):
            return hashlib.md5(item["link"].encode()).hexdigest()[:16]

        # Last resort: title hash
        return hashlib.md5(item.get("title", "").encode()).hexdigest()[:16]

    def _get_published_date(self, item: dict) -> Optional[str]:
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

    def enrich_entry(self, entry: dict) -> dict:
        """Enrich entry with additional data based on source type."""
        raw = entry.pop("_raw", {})

        enriched = {
            "id": entry["id"],
            "source_type": self.source_type,
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published"),
            "author": entry.get("author"),
        }

        if self.source_type in ("blog", "blogs"):
            enriched.update(self._enrich_blog(raw))
        elif self.source_type == "news":
            enriched.update(self._enrich_news(raw, entry))

        return enriched

    def _enrich_podcast(self, raw: dict) -> dict:
        """Extract podcast-specific metadata."""
        data = {
            "summary": raw.get("summary"),
            "content": self._get_content(raw),
        }

        # Extract enclosure (audio file info)
        enclosures = raw.get("enclosures", [])
        if enclosures:
            enc = enclosures[0]
            data["audio"] = {
                "url": enc.get("href") or enc.get("url"),
                "type": enc.get("type"),
                "length": enc.get("length"),
            }

        # Extract iTunes-specific metadata
        if hasattr(raw, "itunes_duration"):
            data["duration"] = raw.itunes_duration
        if hasattr(raw, "itunes_episode"):
            data["episode_number"] = raw.itunes_episode
        if hasattr(raw, "itunes_season"):
            data["season_number"] = raw.itunes_season
        if hasattr(raw, "image"):
            data["image"] = (
                raw.image.get("href") if hasattr(raw.image, "get") else str(raw.image)
            )

        # Tags/categories
        tags = [tag.get("term") for tag in raw.get("tags", []) if tag.get("term")]
        if tags:
            data["tags"] = tags

        return data

    def _enrich_blog(self, raw: dict) -> dict:
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

    def _enrich_news(self, raw: dict, entry: dict) -> dict:
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

    def _get_content(self, raw: dict) -> Optional[str]:
        """Extract main content from entry."""
        # Prefer full content over summary
        if raw.get("content"):
            for content in raw["content"]:
                if content.get("type") in ("text/html", "text/plain"):
                    return content.get("value")

        return raw.get("summary")
