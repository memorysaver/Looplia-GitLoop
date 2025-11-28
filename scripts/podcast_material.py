#!/usr/bin/env python3
"""
Podcast Audio Downloader and Transcriber
Downloads podcast audio and transcribes using WhisperKit or Groq Cloud.
Uses a persistent cache directory to avoid re-downloading audio.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Literal, Optional

import requests

from utils import get_logger

logger = get_logger(__name__)

# Persistent cache directories
# These survive across workflow runs on self-hosted runner
AUDIO_CACHE_DIR = Path.home() / ".cache" / "looplia-gitloop" / "audio"
TRANSCRIPT_CACHE_DIR = Path.home() / ".cache" / "looplia-gitloop" / "transcripts"

# Transcription backend: "groq" (cloud) or "whisperkit" (local)
TRANSCRIPTION_BACKEND = os.environ.get("TRANSCRIPTION_BACKEND", "groq")


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


def get_transcript_cache_path(audio_url: str, episode_id: str) -> Path:
    """
    Get cache path for a transcript file.

    Args:
        audio_url: URL to the audio file (used for hash)
        episode_id: Episode ID

    Returns:
        Path where transcript should be cached (JSON format)
    """
    url_hash = hashlib.md5(audio_url.encode()).hexdigest()[:8]
    return TRANSCRIPT_CACHE_DIR / f"{episode_id}_{url_hash}.json"


def download_and_transcribe(
    audio_url: str, episode_id: str
) -> tuple[Optional[str], Optional[dict]]:
    """
    Download podcast audio and transcribe with WhisperKit or Groq.
    Uses cached transcript or audio if available.
    Backend is selected via TRANSCRIPTION_BACKEND env var ("whisperkit" or "groq").

    Args:
        audio_url: URL to the audio file
        episode_id: Episode ID (for logging)

    Returns:
        Tuple of (transcript_text, raw_data_dict) or (None, None) if failed
        raw_data_dict contains the raw whisper output with timestamps
    """
    if not audio_url:
        logger.warning(f"No audio URL provided for episode: {episode_id}")
        return None, None

    backend = TRANSCRIPTION_BACKEND.lower()
    logger.info(f"Using transcription backend: {backend}")

    # Ensure cache directories exist
    TRANSCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Check transcript cache FIRST - skip transcription entirely if cached
    transcript_cache_path = get_transcript_cache_path(audio_url, episode_id)
    if transcript_cache_path.exists():
        logger.info(f"Using cached transcript for episode: {episode_id}")
        try:
            cached_data = json.loads(transcript_cache_path.read_text())
            raw_output = cached_data.get("raw_output", "")
            cached_backend = cached_data.get("backend", "whisperkit")
            # Use appropriate parser based on cached backend
            if cached_backend == "groq":
                text = parse_groq_output(raw_output)
                # Parse raw_output back to dict for returning
                raw_dict = json.loads(raw_output) if raw_output else None
            else:
                text = parse_whisperkit_output(raw_output)
                raw_dict = {"text": raw_output, "backend": "whisperkit"}
            return text, raw_dict
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid transcript cache for {episode_id}, re-transcribing: {e}")

    # Transcribe based on backend
    if backend == "groq":
        # Groq uses URL directly, no need to download
        raw_output = transcribe_with_groq(audio_url, episode_id)
        parser = parse_groq_output
    else:
        # WhisperKit needs local file
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        audio_cache_path = get_cache_path(audio_url, episode_id)

        if audio_cache_path.exists():
            logger.info(f"Using cached audio for episode: {episode_id}")
            audio_path = audio_cache_path
        else:
            audio_path = download_audio(audio_url, audio_cache_path, episode_id)
            if not audio_path:
                return None, None

        raw_output = transcribe_with_whisperkit_raw(audio_path, episode_id)
        parser = parse_whisperkit_output

    if not raw_output:
        return None, None

    # Save raw output to cache for future runs (include backend info)
    cache_data = {"raw_output": raw_output, "backend": backend}
    transcript_cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))
    logger.info(f"Cached transcript for episode: {episode_id}")

    # Parse and return clean text + raw data
    text = parser(raw_output)
    if backend == "groq":
        raw_dict = json.loads(raw_output)
    else:
        raw_dict = {"text": raw_output, "backend": "whisperkit"}

    return text, raw_dict


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


def transcribe_with_whisperkit_raw(audio_path: Path, episode_id: str) -> Optional[str]:
    """
    Transcribe audio file using WhisperKit CLI and return raw output.

    Args:
        audio_path: Path to audio file
        episode_id: Episode ID (for logging)

    Returns:
        Raw WhisperKit output (with timestamps) or None
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

        raw_output = result.stdout

        if raw_output and raw_output.strip():
            logger.info(f"Transcription complete for {episode_id}")
        else:
            logger.warning(f"Empty transcript for {episode_id}")
            return None

        return raw_output

    except subprocess.TimeoutExpired:
        logger.error(f"WhisperKit timeout for {episode_id}")
        return None
    except FileNotFoundError:
        logger.error("whisperkit-cli not found. Please install WhisperKit.")
        return None
    except Exception as e:
        logger.error(f"Error transcribing {episode_id}: {e}")
        return None


def resolve_redirect_url(url: str) -> str:
    """
    Resolve redirects to get the final URL.
    Groq API doesn't follow redirects, so we need the final URL.

    Args:
        url: Original URL that may redirect

    Returns:
        Final URL after following redirects
    """
    try:
        response = requests.head(url, allow_redirects=True, timeout=30)
        final_url = response.url
        if final_url != url:
            logger.info(f"Resolved redirect: {url[:50]}... -> {final_url[:50]}...")
        return final_url
    except Exception as e:
        logger.warning(f"Failed to resolve redirect for {url}: {e}")
        return url


def transcribe_with_groq(audio_url: str, episode_id: str) -> Optional[str]:
    """
    Transcribe audio using Groq Cloud Whisper API.
    Uses the audio URL directly (no download needed for files >25MB).

    Args:
        audio_url: URL to the audio file
        episode_id: Episode ID (for logging)

    Returns:
        Raw JSON output with timestamps or None
    """
    logger.info(f"Transcribing episode with Groq: {episode_id}")

    try:
        from groq import Groq
    except ImportError:
        logger.error("groq package not installed. Run: pip install groq")
        return None

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY environment variable not set")
        return None

    try:
        client = Groq(api_key=api_key)

        # Resolve redirects first (Groq doesn't follow them)
        final_url = resolve_redirect_url(audio_url)

        # Use URL directly for large files (Groq downloads it)
        transcription = client.audio.transcriptions.create(
            url=final_url,
            model="whisper-large-v3-turbo",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

        # Convert response to JSON string for caching
        if hasattr(transcription, "model_dump"):
            raw_output = json.dumps(transcription.model_dump(), ensure_ascii=False, indent=2)
        else:
            # Fallback for older versions
            raw_output = json.dumps({"text": transcription.text}, ensure_ascii=False, indent=2)

        if raw_output:
            logger.info(f"Groq transcription complete for {episode_id}")
        else:
            logger.warning(f"Empty Groq transcript for {episode_id}")
            return None

        return raw_output

    except Exception as e:
        logger.error(f"Groq transcription failed for {episode_id}: {e}")
        return None


def parse_groq_output(output: str) -> Optional[str]:
    """
    Parse Groq API JSON output to extract transcript text.

    Args:
        output: Raw JSON output from Groq API

    Returns:
        Clean transcript text
    """
    if not output:
        return None

    try:
        data = json.loads(output)
        return data.get("text", "").strip() or None
    except json.JSONDecodeError:
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


def clear_audio_cache():
    """Clear the audio cache directory."""
    if AUDIO_CACHE_DIR.exists():
        import shutil

        shutil.rmtree(AUDIO_CACHE_DIR)
        logger.info("Audio cache cleared")


def clear_transcript_cache():
    """Clear the transcript cache directory."""
    if TRANSCRIPT_CACHE_DIR.exists():
        import shutil

        shutil.rmtree(TRANSCRIPT_CACHE_DIR)
        logger.info("Transcript cache cleared")


def clear_cache():
    """Clear both audio and transcript cache directories."""
    clear_audio_cache()
    clear_transcript_cache()


def get_audio_cache_size() -> int:
    """Get total size of cached audio files in bytes."""
    if not AUDIO_CACHE_DIR.exists():
        return 0
    return sum(f.stat().st_size for f in AUDIO_CACHE_DIR.glob("*") if f.is_file())


def get_transcript_cache_size() -> int:
    """Get total size of cached transcripts in bytes."""
    if not TRANSCRIPT_CACHE_DIR.exists():
        return 0
    return sum(f.stat().st_size for f in TRANSCRIPT_CACHE_DIR.glob("*.json") if f.is_file())


def get_cache_size() -> int:
    """Get total size of all cached files in bytes."""
    return get_audio_cache_size() + get_transcript_cache_size()
