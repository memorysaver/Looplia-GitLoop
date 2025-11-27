#!/usr/bin/env python3
"""
Article Content Extractor
Extracts main article content from web pages using trafilatura.
"""

from typing import Optional

from utils import get_logger

logger = get_logger(__name__)

# Try to import trafilatura
try:
    import trafilatura

    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.warning("trafilatura not available, article extraction will fail")


def extract_article(url: str) -> Optional[str]:
    """
    Fetch and extract main article content from a URL.

    Args:
        url: Article URL

    Returns:
        Clean article text or None if extraction failed
    """
    if not TRAFILATURA_AVAILABLE:
        logger.error("trafilatura is required for article extraction")
        return None

    if not url:
        logger.warning("No URL provided for article extraction")
        return None

    logger.info(f"Extracting article from: {url}")

    try:
        # Fetch the page
        downloaded = trafilatura.fetch_url(url)

        if not downloaded:
            logger.warning(f"Could not fetch URL: {url}")
            return None

        # Extract main content
        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            include_links=False,
            include_images=False,
            output_format="markdown",
            favor_precision=True,
        )

        if content:
            logger.info(f"Extracted {len(content)} characters from article")
            return content.strip()
        else:
            logger.warning(f"No content extracted from: {url}")
            return None

    except Exception as e:
        logger.error(f"Failed to extract article from {url}: {e}")
        return None


def extract_article_with_metadata(url: str) -> Optional[dict]:
    """
    Extract article content along with metadata.

    Args:
        url: Article URL

    Returns:
        Dict with content and metadata or None
    """
    if not TRAFILATURA_AVAILABLE:
        logger.error("trafilatura is required for article extraction")
        return None

    if not url:
        return None

    try:
        downloaded = trafilatura.fetch_url(url)

        if not downloaded:
            return None

        # Extract with metadata
        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            output_format="markdown",
            favor_precision=True,
        )

        # Get metadata separately
        metadata = trafilatura.extract_metadata(downloaded)

        result = {
            "content": content.strip() if content else None,
            "title": metadata.title if metadata else None,
            "author": metadata.author if metadata else None,
            "date": metadata.date if metadata else None,
            "description": metadata.description if metadata else None,
            "sitename": metadata.sitename if metadata else None,
        }

        return result

    except Exception as e:
        logger.error(f"Failed to extract article with metadata from {url}: {e}")
        return None
