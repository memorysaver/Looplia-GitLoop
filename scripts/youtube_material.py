#!/usr/bin/env python3
"""
YouTube Caption/Subtitle Downloader
Downloads and parses captions from YouTube videos.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from core.utils import get_logger

logger = get_logger(__name__)

# Check for browser cookies environment variable
COOKIES_FROM_BROWSER = os.environ.get("YT_COOKIES_FROM_BROWSER", "").strip()

# Try to import yt_dlp
try:
    import yt_dlp

    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logger.warning("yt-dlp not available")


def download_captions(
    video_id: str, languages: list = None, prefer_manual: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """
    Download captions for a YouTube video.

    Args:
        video_id: YouTube video ID
        languages: List of preferred languages (default: ["en"])
        prefer_manual: Prefer manual captions over auto-generated

    Returns:
        Tuple of (plain_text_transcript, raw_vtt_content) or (None, None) if not available
    """
    if not YTDLP_AVAILABLE:
        logger.error("yt-dlp is required for caption download")
        return None, None

    if languages is None:
        languages = ["en"]

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": languages,
            "subtitlesformat": "vtt",
            "outtmpl": str(temp_path / "%(id)s.%(ext)s"),
        }

        # Use browser cookies if available
        if COOKIES_FROM_BROWSER:
            ydl_opts["cookiesfrombrowser"] = (COOKIES_FROM_BROWSER,)
            logger.info(f"Using cookies from browser: {COOKIES_FROM_BROWSER}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

                if not info:
                    logger.warning(f"Could not get info for video: {video_id}")
                    return None

                # Check available captions
                subtitles = info.get("subtitles", {})
                auto_captions = info.get("automatic_captions", {})

                # Find best caption source
                selected_lang = None
                is_auto = False

                for lang in languages:
                    # Check manual subtitles first if preferred
                    if prefer_manual and lang in subtitles:
                        selected_lang = lang
                        break
                    # Try language variants (e.g., 'en-US' for 'en')
                    if prefer_manual:
                        for sub_lang in subtitles:
                            if sub_lang.startswith(lang):
                                selected_lang = sub_lang
                                break
                    if selected_lang:
                        break

                    # Check auto captions
                    if lang in auto_captions:
                        selected_lang = lang
                        is_auto = True
                        break
                    for auto_lang in auto_captions:
                        if auto_lang.startswith(lang):
                            selected_lang = auto_lang
                            is_auto = True
                            break
                    if selected_lang:
                        break

                if not selected_lang:
                    logger.warning(f"No captions found for video: {video_id}")
                    return None, None

                logger.info(
                    f"Downloading {'auto' if is_auto else 'manual'} captions "
                    f"({selected_lang}) for {video_id}"
                )

                # Download the subtitles
                ydl_opts["subtitleslangs"] = [selected_lang]
                if is_auto:
                    ydl_opts["writesubtitles"] = False
                else:
                    ydl_opts["writeautomaticsub"] = False

                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    ydl2.download([video_url])

                # Find the downloaded subtitle file
                vtt_files = list(temp_path.glob(f"{video_id}*.vtt"))
                if not vtt_files:
                    logger.warning(f"No VTT file found for video: {video_id}")
                    return None, None

                # Read VTT content before parsing
                vtt_content = vtt_files[0].read_text(encoding='utf-8')

                # Parse VTT and extract text
                transcript = parse_vtt(vtt_files[0])
                return transcript, vtt_content

        except Exception as e:
            logger.error(f"Failed to download captions for {video_id}: {e}")
            return None, None


def parse_vtt(vtt_path: Path) -> str:
    """
    Parse VTT file and extract plain text transcript.

    Args:
        vtt_path: Path to VTT file

    Returns:
        Clean transcript text
    """
    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = []
    seen_lines = set()  # For deduplication

    # Skip header
    in_cue = False
    for line in content.split("\n"):
        line = line.strip()

        # Skip empty lines and header
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:"):
            in_cue = False
            continue

        # Skip NOTE lines
        if line.startswith("NOTE"):
            continue

        # Skip timestamp lines
        if "-->" in line:
            in_cue = True
            continue

        # Skip cue identifiers (usually numbers)
        if line.isdigit():
            continue

        if in_cue:
            # Remove VTT formatting tags
            clean_line = re.sub(r"<[^>]+>", "", line)
            # Remove position/alignment info
            clean_line = re.sub(r"\{[^}]+\}", "", clean_line)
            clean_line = clean_line.strip()

            if clean_line and clean_line not in seen_lines:
                lines.append(clean_line)
                seen_lines.add(clean_line)

    # Join lines into paragraphs
    # Group consecutive lines, separate by empty lines for readability
    transcript = "\n".join(lines)

    # Clean up multiple spaces/newlines
    transcript = re.sub(r"\n{3,}", "\n\n", transcript)
    transcript = re.sub(r" {2,}", " ", transcript)

    return transcript.strip()
