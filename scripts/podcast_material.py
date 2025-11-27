#!/usr/bin/env python3
"""
Podcast Audio Downloader and Transcriber
Downloads podcast audio and transcribes using WhisperKit.
Uses a persistent cache directory to avoid re-downloading audio.
"""

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Optional

import requests

from utils import get_logger

logger = get_logger(__name__)

# Persistent cache directory for downloaded audio
# This survives across workflow runs on self-hosted runner
AUDIO_CACHE_DIR = Path.home() / ".cache" / "looplia-gitloop" / "audio"


def get_cache_path(audio_url: str, episode_id: str) -> Path:
    """
    Get cache path for an audio file.

    Args:
        audio_url: URL to the audio file
        episode_id: Episode ID

    Returns:
        Path where audio should be cached
    """
    # Use URL hash to handle different URLs for same episode
    url_hash = hashlib.md5(audio_url.encode()).hexdigest()[:8]

    # Determine extension
    ext = ".mp3"
    if ".m4a" in audio_url.lower():
        ext = ".m4a"
    elif ".wav" in audio_url.lower():
        ext = ".wav"
    elif ".aac" in audio_url.lower():
        ext = ".aac"

    return AUDIO_CACHE_DIR / f"{episode_id}_{url_hash}{ext}"


def download_and_transcribe(audio_url: str, episode_id: str) -> Optional[str]:
    """
    Download podcast audio and transcribe with WhisperKit.
    Uses cached audio if available.

    Args:
        audio_url: URL to the audio file
        episode_id: Episode ID (for logging)

    Returns:
        Transcript text or None if failed
    """
    if not audio_url:
        logger.warning(f"No audio URL provided for episode: {episode_id}")
        return None

    # Ensure cache directory exists
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Check cache
    cache_path = get_cache_path(audio_url, episode_id)

    if cache_path.exists():
        logger.info(f"Using cached audio for episode: {episode_id}")
        audio_path = cache_path
    else:
        # Download audio file to cache
        audio_path = download_audio(audio_url, cache_path, episode_id)
        if not audio_path:
            return None

    # Transcribe with WhisperKit
    transcript = transcribe_with_whisperkit(audio_path, episode_id)

    # Optionally clean up cache after successful transcription
    # Uncomment if you want to delete audio after transcribing:
    # if transcript and cache_path.exists():
    #     cache_path.unlink()
    #     logger.info(f"Cleaned up cached audio for: {episode_id}")

    return transcript


def download_audio(url: str, dest_path: Path, episode_id: str) -> Optional[Path]:
    """
    Download audio file to destination path.

    Args:
        url: Audio URL
        dest_path: Destination file path
        episode_id: Episode ID for logging

    Returns:
        Path to downloaded file or None
    """
    logger.info(f"Downloading audio for episode: {episode_id}")

    try:
        # Download with streaming
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get("content-type", "")
        if "audio" not in content_type and "octet-stream" not in content_type:
            logger.warning(f"Unexpected content type: {content_type}")

        # Write to file
        total_size = 0
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)

        logger.info(f"Downloaded {total_size / 1024 / 1024:.1f} MB to cache")
        return dest_path

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download audio for {episode_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error downloading audio for {episode_id}: {e}")
        return None


def transcribe_with_whisperkit(audio_path: Path, episode_id: str) -> Optional[str]:
    """
    Transcribe audio file using WhisperKit CLI.

    Args:
        audio_path: Path to audio file
        episode_id: Episode ID (for logging)

    Returns:
        Transcript text or None
    """
    logger.info(f"Transcribing episode: {episode_id}")

    try:
        # Run WhisperKit CLI
        # whisperkit-cli transcribe --audio-path <file> --model-path <model>
        result = subprocess.run(
            [
                "whisperkit-cli",
                "transcribe",
                "--audio-path",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout for long podcasts
        )

        if result.returncode != 0:
            logger.error(f"WhisperKit failed for {episode_id}: {result.stderr}")
            return None

        # Parse output
        transcript = parse_whisperkit_output(result.stdout)

        if transcript:
            logger.info(f"Transcription complete for {episode_id}")
        else:
            logger.warning(f"Empty transcript for {episode_id}")

        return transcript

    except subprocess.TimeoutExpired:
        logger.error(f"WhisperKit timeout for {episode_id}")
        return None
    except FileNotFoundError:
        logger.error("whisperkit-cli not found. Please install WhisperKit.")
        return None
    except Exception as e:
        logger.error(f"Error transcribing {episode_id}: {e}")
        return None


def parse_whisperkit_output(output: str) -> Optional[str]:
    """
    Parse WhisperKit CLI output to extract transcript text.

    Args:
        output: Raw CLI output

    Returns:
        Clean transcript text
    """
    if not output:
        return None

    # WhisperKit output format may vary
    # Try to extract just the text content
    lines = []

    for line in output.strip().split("\n"):
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip timestamp lines (e.g., "[00:00:00 -> 00:00:05]")
        if line.startswith("[") and "->" in line:
            continue

        # Skip metadata/progress lines
        if line.startswith("Loading") or line.startswith("Processing"):
            continue

        lines.append(line)

    transcript = "\n".join(lines)
    return transcript.strip() if transcript else None


def clear_cache():
    """Clear the audio cache directory."""
    if AUDIO_CACHE_DIR.exists():
        import shutil

        shutil.rmtree(AUDIO_CACHE_DIR)
        logger.info("Audio cache cleared")


def get_cache_size() -> int:
    """Get total size of cached audio files in bytes."""
    if not AUDIO_CACHE_DIR.exists():
        return 0
    return sum(f.stat().st_size for f in AUDIO_CACHE_DIR.glob("*") if f.is_file())
