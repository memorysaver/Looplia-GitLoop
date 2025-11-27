#!/usr/bin/env python3
"""
Podcast Handler - Hybrid RSS + yt-dlp approach for podcasts.
Supports Apple Podcasts, Spotify, and direct RSS feeds.
"""

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import feedparser
import requests

from utils import get_logger, sanitize_id

logger = get_logger(__name__)

# Check for browser cookies environment variable
COOKIES_FROM_BROWSER = os.environ.get("YT_COOKIES_FROM_BROWSER", "").strip()

# Try to import yt_dlp, but don't fail if not available
try:
    import yt_dlp

    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logger.warning("yt-dlp not available, podcast enrichment will be limited")


class PodcastHandler:
    """Handler for podcasts using RSS discovery + optional yt-dlp enrichment."""

    def __init__(self, source_config: dict):
        self.config = source_config
        self.options = source_config.get("options", {})
        self.url = source_config["url"]
        self.source_type = source_config["type"]
        self.use_ytdlp = self.options.get("use_ytdlp", False) and YTDLP_AVAILABLE

    def _is_apple_podcasts_url(self, url: str) -> bool:
        """Check if URL is an Apple Podcasts URL."""
        parsed = urlparse(url)
        return "podcasts.apple.com" in parsed.netloc

    def _extract_apple_podcast_id(self, url: str) -> Optional[str]:
        """Extract podcast ID from Apple Podcasts URL."""
        # URL format: https://podcasts.apple.com/tw/podcast/name/id1498541229
        match = re.search(r"/id(\d+)", url)
        if match:
            return match.group(1)
        return None

    def _get_rss_feed_url(self) -> Optional[str]:
        """Get RSS feed URL for the podcast."""
        # If already an RSS URL, return as-is
        if self.url.endswith(".xml") or self.url.endswith(".rss"):
            return self.url

        # For Apple Podcasts, use iTunes Search API to get RSS feed
        if self._is_apple_podcasts_url(self.url):
            podcast_id = self._extract_apple_podcast_id(self.url)
            if podcast_id:
                try:
                    api_url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast"
                    response = requests.get(api_url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        results = data.get("results", [])
                        if results:
                            return results[0].get("feedUrl")
                except Exception as e:
                    logger.error(f"Failed to get RSS feed from iTunes API: {e}")

        # Fallback: return the original URL and hope it's an RSS feed
        return self.url

    def fetch_entries(self, archived_ids: set) -> list:
        """Fetch new podcast episodes."""
        rss_url = self._get_rss_feed_url()
        if not rss_url:
            logger.error(f"Could not determine RSS feed URL for {self.url}")
            return []

        logger.info(f"Fetching RSS feed: {rss_url}")
        feed = feedparser.parse(rss_url)

        if feed.bozo and feed.bozo_exception:
            logger.warning(f"Feed parsing warning: {feed.bozo_exception}")

        entries = []
        for item in feed.entries:
            entry_id = self._get_entry_id(item)

            if entry_id not in archived_ids:
                # Build Apple Podcasts episode URL if available
                apple_episode_url = None
                if self._is_apple_podcasts_url(self.url):
                    podcast_id = self._extract_apple_podcast_id(self.url)
                    # Try to extract episode ID from item
                    episode_id = item.get("id", "")
                    if podcast_id and episode_id:
                        # Some feeds include the episode ID in a format we can use
                        apple_episode_url = f"https://podcasts.apple.com/podcast/id{podcast_id}?i={entry_id}"

                entries.append(
                    {
                        "id": entry_id,
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "published": self._get_published_date(item),
                        "author": item.get("author"),
                        "summary": item.get("summary"),
                        "apple_url": apple_episode_url,
                        "_raw": item,
                    }
                )

        return entries

    def _get_entry_id(self, item: dict) -> str:
        """Generate a unique ID for the episode."""
        # Prefer GUID
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
        """Enrich episode with metadata, optionally using yt-dlp."""
        raw = entry.pop("_raw", {})
        apple_url = entry.pop("apple_url", None)

        enriched = {
            "id": entry["id"],
            "source_type": "podcast",
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published"),
            "author": entry.get("author"),
        }

        # Try yt-dlp enrichment for Apple Podcasts
        if self.use_ytdlp and apple_url:
            ytdlp_data = self._enrich_with_ytdlp(apple_url)
            if ytdlp_data:
                enriched.update(ytdlp_data)
                return enriched

        # Fallback to RSS data enrichment
        enriched.update(self._enrich_from_rss(raw))
        return enriched

    def _enrich_with_ytdlp(self, url: str) -> Optional[dict]:
        """Use yt-dlp to get detailed episode metadata."""
        if not YTDLP_AVAILABLE:
            return None

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }

        # Use browser cookies if available
        if COOKIES_FROM_BROWSER:
            ydl_opts["cookiesfrombrowser"] = (COOKIES_FROM_BROWSER,)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    sanitized = ydl.sanitize_info(info)
                    return {
                        "title": sanitized.get("title"),
                        "description": sanitized.get("description"),
                        "duration": sanitized.get("duration"),
                        "duration_string": sanitized.get("duration_string"),
                        "thumbnail": sanitized.get("thumbnail"),
                        "audio_url": sanitized.get("url"),
                        "episode_number": sanitized.get("episode_number"),
                        "season_number": sanitized.get("season_number"),
                        "series": sanitized.get("series"),
                        "enriched_via": "ytdlp",
                    }
        except Exception as e:
            logger.warning(f"yt-dlp enrichment failed for {url}: {e}")

        return None

    def _enrich_from_rss(self, raw: dict) -> dict:
        """Extract metadata from RSS feed data."""
        data = {
            "summary": raw.get("summary"),
            "content": self._get_content(raw),
            "enriched_via": "rss",
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

        # Also check for itunes_ prefixed attributes in the dict
        for key in ["itunes_duration", "itunes_episode", "itunes_season", "itunes_image"]:
            if key in raw:
                clean_key = key.replace("itunes_", "")
                if clean_key == "image":
                    data["image"] = raw[key].get("href", raw[key]) if isinstance(raw[key], dict) else raw[key]
                else:
                    data[clean_key] = raw[key]

        # Tags/categories
        tags = [tag.get("term") for tag in raw.get("tags", []) if tag.get("term")]
        if tags:
            data["tags"] = tags

        return data

    def _get_content(self, raw: dict) -> Optional[str]:
        """Extract main content from entry."""
        if raw.get("content"):
            for content in raw["content"]:
                if content.get("type") in ("text/html", "text/plain"):
                    return content.get("value")

        return raw.get("summary")
