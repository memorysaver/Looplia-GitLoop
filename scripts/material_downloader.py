#!/usr/bin/env python3
"""
Writing Materials Downloader
Processes archived subscriptions and downloads detailed content as markdown files.
Uses persistent cache to track processed items across runs.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from article_material import extract_article
from podcast_material import download_and_transcribe
from utils import get_logger, load_json
from youtube_material import download_captions

logger = get_logger(__name__)

# Base paths
BASE_DIR = Path(__file__).parent.parent
SUBSCRIPTIONS_DIR = BASE_DIR / "subscriptions"
MATERIALS_DIR = BASE_DIR / "writing-materials"

# Persistent cache for tracking processed items (survives failed runs)
CACHE_DIR = Path.home() / ".cache" / "looplia-gitloop"
PROCESSED_CACHE_FILE = CACHE_DIR / "processed_materials.json"


class MaterialDownloader:
    """Downloads and processes writing materials from archived subscriptions."""

    def __init__(self):
        self.subscriptions_dir = SUBSCRIPTIONS_DIR
        self.materials_dir = MATERIALS_DIR
        self.processed_cache = self._load_processed_cache()

    def _load_processed_cache(self) -> dict:
        """Load the persistent cache of processed item IDs."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if PROCESSED_CACHE_FILE.exists():
            try:
                with open(PROCESSED_CACHE_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load processed cache: {e}")
        return {}

    def _save_processed_cache(self):
        """Save the processed cache to disk."""
        try:
            with open(PROCESSED_CACHE_FILE, "w") as f:
                json.dump(self.processed_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save processed cache: {e}")

    def _mark_as_processed(self, source_type: str, source_key: str, entry_id: str):
        """Mark an item as processed in the cache."""
        cache_key = f"{source_type}/{source_key}"
        if cache_key not in self.processed_cache:
            self.processed_cache[cache_key] = []
        if entry_id not in self.processed_cache[cache_key]:
            self.processed_cache[cache_key].append(entry_id)
            self._save_processed_cache()  # Save immediately after each item

    def _is_processed(self, source_type: str, source_key: str, entry_id: str) -> bool:
        """Check if an item has already been processed."""
        cache_key = f"{source_type}/{source_key}"
        return entry_id in self.processed_cache.get(cache_key, [])

    def process_all(self, source_type: str = None, source_key: str = None):
        """
        Process all or specific sources.

        Args:
            source_type: Optional filter by type (youtube, podcast, blogs, news)
            source_key: Optional filter by specific source key
        """
        types_to_process = (
            [source_type] if source_type else ["youtube", "podcast", "blogs", "news"]
        )

        total_processed = 0

        for stype in types_to_process:
            type_dir = self.subscriptions_dir / stype
            if not type_dir.exists():
                continue

            for source_dir in type_dir.iterdir():
                if not source_dir.is_dir():
                    continue

                if source_key and source_dir.name != source_key:
                    continue

                count = self.process_source(stype, source_dir.name)
                total_processed += count

        logger.info(f"Material download complete. Total processed: {total_processed}")

    def process_source(self, source_type: str, source_key: str) -> int:
        """
        Process a single source.

        Args:
            source_type: Type of source
            source_key: Source key/identifier

        Returns:
            Number of materials processed
        """
        logger.info(f"Processing {source_type}/{source_key}")

        # Load index to get archived entries
        index_path = self.subscriptions_dir / source_type / source_key / "index.json"
        if not index_path.exists():
            logger.warning(f"No index found for {source_type}/{source_key}")
            return 0

        index = load_json(index_path)
        if not index:
            return 0

        # Get already processed IDs
        processed_ids = self.get_processed_ids(source_type, source_key)

        # Create output directory
        output_dir = self.materials_dir / source_type / source_key
        output_dir.mkdir(parents=True, exist_ok=True)

        processed = 0

        for entry_info in index.get("entries", []):
            entry_id = entry_info.get("id")

            if not entry_id or entry_id in processed_ids:
                continue

            # Load full entry data
            entry_path = (
                self.subscriptions_dir / source_type / source_key / f"{entry_id}.json"
            )
            if not entry_path.exists():
                continue

            entry = load_json(entry_path)
            if not entry:
                continue

            # Download/extract content based on type
            content = self.extract_content(source_type, entry)

            if content:
                # Save as markdown
                self.save_markdown(output_dir, entry, content, source_type, source_key)
                # Mark as processed in persistent cache
                self._mark_as_processed(source_type, source_key, entry_id)
                processed += 1
                logger.info(f"Processed: {entry.get('title', entry_id)}")
            else:
                logger.warning(f"No content extracted for: {entry_id}")

        return processed

    def get_processed_ids(self, source_type: str, source_key: str) -> set:
        """Get IDs of already processed materials (from files + cache)."""
        processed = set()

        # Check existing .md files in repo
        materials_path = self.materials_dir / source_type / source_key
        if materials_path.exists():
            processed.update(f.stem for f in materials_path.glob("*.md"))

        # Also check persistent cache (for items processed in failed runs)
        cache_key = f"{source_type}/{source_key}"
        processed.update(self.processed_cache.get(cache_key, []))

        return processed

    def extract_content(self, source_type: str, entry: dict) -> str | None:
        """
        Extract content based on source type.

        Args:
            source_type: Type of source
            entry: Entry data from subscription

        Returns:
            Extracted content or None
        """
        if source_type == "youtube":
            return self.extract_youtube(entry)
        elif source_type == "podcast":
            return self.extract_podcast(entry)
        elif source_type in ("blogs", "news"):
            return self.extract_article(entry)
        else:
            logger.warning(f"Unknown source type: {source_type}")
            return None

    def extract_youtube(self, entry: dict) -> str | None:
        """Extract YouTube captions."""
        video_id = entry.get("id")
        if not video_id:
            return None

        # Get language preference from entry or default to English
        languages = entry.get("transcript_languages", ["en"])

        return download_captions(video_id, languages=languages)

    def extract_podcast(self, entry: dict) -> str | None:
        """Extract podcast transcript via audio download + WhisperKit."""
        episode_id = entry.get("id")

        # Get audio URL from entry
        audio_url = None

        # Check various places where audio URL might be stored
        if entry.get("audio_url"):
            audio_url = entry["audio_url"]
        elif entry.get("audio") and isinstance(entry["audio"], dict):
            audio_url = entry["audio"].get("url")

        if not audio_url:
            logger.warning(f"No audio URL found for podcast episode: {episode_id}")
            return None

        return download_and_transcribe(audio_url, episode_id)

    def extract_article(self, entry: dict) -> str | None:
        """Extract article content."""
        url = entry.get("link") or entry.get("url")

        if not url:
            logger.warning(f"No URL found for article: {entry.get('id')}")
            return None

        return extract_article(url)

    def save_markdown(
        self,
        output_dir: Path,
        entry: dict,
        content: str,
        source_type: str,
        source_key: str,
    ):
        """
        Save content as markdown file with frontmatter.

        Args:
            output_dir: Directory to save to
            entry: Entry metadata
            content: Extracted content
            source_type: Type of source
            source_key: Source key
        """
        entry_id = entry.get("id")
        title = entry.get("title", "Untitled")
        url = entry.get("url") or entry.get("link", "")
        published = entry.get("published", "")

        # Escape title for YAML
        escaped_title = title.replace('"', '\\"')
        downloaded_at = datetime.now(timezone.utc).isoformat()

        # Build markdown with frontmatter
        markdown = f"""---
id: {entry_id}
source_type: {source_type}
source_key: {source_key}
title: "{escaped_title}"
url: {url}
published: {published}
downloaded_at: {downloaded_at}
---

# {title}

{content}
"""

        # Save file
        output_path = output_dir / f"{entry_id}.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)


def main():
    """Main entry point."""
    # Get filters from environment
    source_type = os.environ.get("SOURCE_TYPE", "").strip() or None
    source_key = os.environ.get("SOURCE_KEY", "").strip() or None

    if source_type:
        logger.info(f"Filtering by type: {source_type}")
    if source_key:
        logger.info(f"Filtering by key: {source_key}")

    downloader = MaterialDownloader()
    downloader.process_all(source_type=source_type, source_key=source_key)


if __name__ == "__main__":
    main()
