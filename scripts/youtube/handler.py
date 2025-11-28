#!/usr/bin/env python3
"""
YouTube Handler - Uses yt-dlp to extract metadata and transcripts.
Extends BaseSubscriptionHandler for YouTube-specific behavior.
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

import feedparser
import yt_dlp

# Add parent directory to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base_handler import BaseSubscriptionHandler
from core.utils import get_logger

logger = get_logger(__name__)

# Check for browser cookies environment variable
COOKIES_FROM_BROWSER = os.environ.get("YT_COOKIES_FROM_BROWSER", "").strip()


class YouTubeHandler(BaseSubscriptionHandler):
    """Handler for YouTube channels and playlists."""

    @property
    def source_type(self) -> str:
        """Return source type identifier."""
        return "youtube"

    def _get_channel_id(self) -> Optional[str]:
        """Extract channel ID from YouTube URL using yt-dlp."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": "0",
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                return info.get("channel_id") or info.get("uploader_id")
        except Exception as e:
            logger.error(f"Failed to get channel ID: {e}")
            return None

    def _get_rss_feed_url(self) -> Optional[str]:
        """Get YouTube RSS feed URL for the channel."""
        channel_id = self._get_channel_id()
        if channel_id:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        return None

    def fetch_entries(self, archived_ids: Set[str]) -> List[Dict]:
        """
        Fetch new video entries from YouTube.
        Uses RSS feed for efficiency, then yt-dlp for detailed metadata.
        """
        entries = []

        if self.source_type == "youtube":  # Channels
            # Use RSS feed for recent videos (last 15)
            rss_url = self._get_rss_feed_url()
            if rss_url:
                feed = feedparser.parse(rss_url)
                for item in feed.entries:
                    video_id = item.get("yt_videoid") or self._extract_video_id(
                        item.get("link", "")
                    )
                    if video_id and video_id not in archived_ids:
                        entries.append(
                            {
                                "id": video_id,
                                "url": f"https://www.youtube.com/watch?v={video_id}",
                                "title": item.get("title"),
                                "published": item.get("published"),
                                "author": item.get("author"),
                            }
                        )
        else:
            # For playlists, use yt-dlp flat extraction
            entries = self._fetch_via_ytdlp(archived_ids)

        return entries

    def _fetch_via_ytdlp(self, archived_ids: Set[str]) -> List[Dict]:
        """Fetch entries using yt-dlp (for playlists or fallback)."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "ignoreerrors": True,
        }

        entries = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)

                for item in info.get("entries", []):
                    if item is None:
                        continue
                    video_id = item.get("id")
                    if video_id and video_id not in archived_ids:
                        entries.append(
                            {
                                "id": video_id,
                                "url": item.get("url")
                                or f"https://www.youtube.com/watch?v={video_id}",
                                "title": item.get("title"),
                            }
                        )
        except Exception as e:
            logger.error(f"yt-dlp fetch failed: {e}")

        return entries

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL."""
        patterns = [
            r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def enrich_entry(self, entry: Dict) -> Optional[Dict]:
        """
        Enrich entry with full metadata and transcript using yt-dlp.
        """
        video_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"

        # yt-dlp options for metadata extraction
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": self.options.get("extract_transcript", True),
            "writeautomaticsub": self.options.get("extract_transcript", True),
            "subtitleslangs": self.options.get("transcript_languages", ["en"]),
            "subtitlesformat": "json3",
        }

        # Use browser cookies if available (for self-hosted runners)
        if COOKIES_FROM_BROWSER:
            ydl_opts["cookiesfrombrowser"] = (COOKIES_FROM_BROWSER,)
            logger.info(f"Using cookies from browser: {COOKIES_FROM_BROWSER}")

        enriched = {
            "id": entry["id"],
            "source_type": "youtube",
            "url": video_url,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                sanitized = ydl.sanitize_info(info)

                # Skip Shorts (videos ≤60 seconds)
                duration = sanitized.get("duration")
                if duration is not None and duration <= 60:
                    logger.info(f"Skipping Short (duration: {duration}s): {entry['id']}")
                    return None

                # Extract relevant metadata
                enriched.update(
                    {
                        "title": sanitized.get("title"),
                        "description": sanitized.get("description"),
                        "channel": sanitized.get("channel"),
                        "channel_id": sanitized.get("channel_id"),
                        "channel_url": sanitized.get("channel_url"),
                        "uploader": sanitized.get("uploader"),
                        "duration": sanitized.get("duration"),
                        "duration_string": sanitized.get("duration_string"),
                        "view_count": sanitized.get("view_count"),
                        "like_count": sanitized.get("like_count"),
                        "comment_count": sanitized.get("comment_count"),
                        "published": sanitized.get("upload_date"),
                        "thumbnail": sanitized.get("thumbnail"),
                        "thumbnails": self._extract_thumbnails(
                            sanitized.get("thumbnails", [])
                        ),
                        "tags": sanitized.get("tags", []),
                        "categories": sanitized.get("categories", []),
                        "chapters": sanitized.get("chapters", []),
                    }
                )

                # Extract transcript from automatic captions
                if self.options.get("extract_transcript", True):
                    transcript = self._extract_transcript(sanitized)
                    if transcript:
                        enriched["transcript"] = transcript

        except Exception as e:
            logger.error(f"Failed to enrich entry {entry['id']}: {e}")
            # Return basic entry data on failure
            enriched.update(entry)

        return enriched

    def _extract_thumbnails(self, thumbnails: list) -> list:
        """Extract simplified thumbnail data."""
        return [
            {
                "url": t.get("url"),
                "width": t.get("width"),
                "height": t.get("height"),
            }
            for t in thumbnails
            if t.get("url")
        ][:5]  # Limit to 5 thumbnails

    def _extract_transcript(self, info: Dict) -> Optional[Dict]:
        """
        Extract transcript from automatic captions.
        Returns structured transcript data.
        """
        # Check for automatic captions
        auto_captions = info.get("automatic_captions", {})
        subtitles = info.get("subtitles", {})

        # Prefer manual subtitles over auto-generated
        captions = subtitles or auto_captions

        if not captions:
            return None

        # Find preferred language
        preferred_langs = self.options.get("transcript_languages", ["en"])

        selected_caption = None
        selected_lang = None

        for lang in preferred_langs:
            if lang in captions:
                selected_caption = captions[lang]
                selected_lang = lang
                break
            # Try language variants (e.g., 'en-US' for 'en')
            for caption_lang in captions:
                if caption_lang.startswith(lang):
                    selected_caption = captions[caption_lang]
                    selected_lang = caption_lang
                    break
            if selected_caption:
                break

        if not selected_caption:
            # Fallback to first available
            selected_lang = list(captions.keys())[0]
            selected_caption = captions[selected_lang]

        # Return metadata about available transcript
        return {
            "available": True,
            "language": selected_lang,
            "auto_generated": bool(auto_captions and not subtitles),
            "formats": [f.get("ext") for f in selected_caption if f.get("ext")],
        }
