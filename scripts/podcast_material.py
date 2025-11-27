#!/usr/bin/env python3
"""
Podcast Audio Downloader and Transcriber
Downloads podcast audio and transcribes using WhisperKit.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import requests

from utils import get_logger

logger = get_logger(__name__)


def download_and_transcribe(audio_url: str, episode_id: str) -> Optional[str]:
    """
    Download podcast audio and transcribe with WhisperKit.

    Args:
        audio_url: URL to the audio file
        episode_id: Episode ID (for logging)

    Returns:
        Transcript text or None if failed
    """
    if not audio_url:
        logger.warning(f"No audio URL provided for episode: {episode_id}")
        return None

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Download audio file
        audio_path = download_audio(audio_url, temp_path, episode_id)
        if not audio_path:
            return None

        # Transcribe with WhisperKit
        transcript = transcribe_with_whisperkit(audio_path, episode_id)
        return transcript


def download_audio(url: str, temp_dir: Path, episode_id: str) -> Optional[Path]:
    """
    Download audio file to temp directory.

    Args:
        url: Audio URL
        temp_dir: Temporary directory path
        episode_id: Episode ID for filename

    Returns:
        Path to downloaded file or None
    """
    logger.info(f"Downloading audio for episode: {episode_id}")

    try:
        # Determine file extension from URL or content-type
        ext = ".mp3"  # Default
        if ".m4a" in url.lower():
            ext = ".m4a"
        elif ".wav" in url.lower():
            ext = ".wav"
        elif ".aac" in url.lower():
            ext = ".aac"

        audio_path = temp_dir / f"{episode_id}{ext}"

        # Download with streaming
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get("content-type", "")
        if "audio" not in content_type and "octet-stream" not in content_type:
            logger.warning(f"Unexpected content type: {content_type}")

        # Write to file
        total_size = 0
        with open(audio_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)

        logger.info(f"Downloaded {total_size / 1024 / 1024:.1f} MB")
        return audio_path

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
