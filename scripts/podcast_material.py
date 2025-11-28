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

from core.utils import get_logger

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
    raw_output = None
    parser = None

    if backend == "groq":
        # Check file size
        file_size = get_file_size(audio_url)

        if not file_size or file_size < 104857600:  # < 100MB or unknown
            # Use direct URL method (Groq downloads file)
            raw_output = transcribe_with_groq(audio_url, episode_id)
            parser = parse_groq_output

        else:  # >= 100MB - use chunking approach
            logger.info(f"Large file detected ({file_size / 1024 / 1024:.1f}MB), using chunking")

            # Download audio to cache
            AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            audio_cache_path = get_cache_path(audio_url, episode_id)

            if audio_cache_path.exists():
                logger.info(f"Using cached audio for chunking: {episode_id}")
                audio_path = audio_cache_path
            else:
                audio_path = download_audio(audio_url, audio_cache_path, episode_id)
                if not audio_path:
                    return None, None

            # Chunk and transcribe
            raw_output = transcribe_with_groq_chunked(audio_path, episode_id)
            parser = parse_groq_output

    # Use WhisperKit if requested or if Groq fallback was triggered
    if backend == "whisperkit":
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


def get_file_size(url: str) -> Optional[int]:
    """
    Get file size from URL via HEAD request.

    Args:
        url: URL to check

    Returns:
        File size in bytes or None if unable to determine
    """
    try:
        response = requests.head(url, allow_redirects=True, timeout=30)
        size = response.headers.get("content-length")
        if size:
            return int(size)
    except Exception as e:
        logger.warning(f"Failed to get file size for {url}: {e}")
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


def chunk_audio(
    audio_path: Path,
    chunk_duration_ms: int = 600000,  # 10 minutes
    overlap_ms: int = 10000,  # 10 seconds
) -> list[Path]:
    """
    Split audio file into overlapping chunks using PyDub.

    Args:
        audio_path: Path to audio file
        chunk_duration_ms: Chunk size in milliseconds (default: 10 min)
        overlap_ms: Overlap size in milliseconds (default: 10 sec)

    Returns:
        List of paths to chunk files
    """
    from pydub import AudioSegment

    logger.info(f"Chunking audio file: {audio_path.name} ({audio_path.stat().st_size / 1024 / 1024:.1f}MB)")

    # Load audio (PyDub automatically uses FFmpeg)
    audio = AudioSegment.from_file(str(audio_path))

    chunks = []
    start = 0
    chunk_num = 0

    while start < len(audio):
        end = min(start + chunk_duration_ms, len(audio))
        chunk = audio[start:end]

        # Save chunk to temp file
        chunk_path = audio_path.parent / f"{audio_path.stem}_chunk_{chunk_num}.mp3"
        chunk.export(str(chunk_path), format="mp3")
        chunks.append(chunk_path)

        logger.info(f"Created chunk {chunk_num + 1}: {chunk_path.name}")

        chunk_num += 1
        start += chunk_duration_ms - overlap_ms  # Move forward with overlap

    logger.info(f"Chunked into {len(chunks)} pieces")
    return chunks


def find_overlap(text1: str, text2: str, min_overlap: int = 20) -> int:
    """
    Find overlap between end of text1 and start of text2.

    Uses sliding window with word-level matching.

    Args:
        text1: First text (merged so far)
        text2: Second text (current chunk)
        min_overlap: Minimum overlap length in characters

    Returns:
        Length of overlap in characters from start of text2
    """
    if not text1 or not text2:
        return 0

    # Extract last portion of text1 (search window)
    window_size = 500  # Check last 500 chars
    search_text = text1[-window_size:] if len(text1) > window_size else text1

    # Split into words for matching
    words1 = search_text.split()
    words2 = text2.split()

    if not words1 or not words2:
        return 0

    best_overlap = 0

    # Try different overlap lengths
    for overlap_words in range(min(len(words1), len(words2)), 0, -1):
        # Check if last N words of text1 match first N words of text2
        if words1[-overlap_words:] == words2[:overlap_words]:
            # Calculate character length
            best_overlap = len(" ".join(words2[:overlap_words]))
            break

    return best_overlap if best_overlap >= min_overlap else 0


def merge_transcripts(transcript_chunks: list[dict]) -> str:
    """
    Merge overlapping transcript chunks using longest common sequence.

    Based on Groq community article approach:
    - Uses sliding window to find overlap between consecutive chunks
    - Matches words/characters with weighted scoring
    - Handles partial matches at chunk boundaries

    Args:
        transcript_chunks: List of transcript dicts with 'text' field

    Returns:
        Merged transcript text
    """
    if not transcript_chunks:
        return ""

    if len(transcript_chunks) == 1:
        text = transcript_chunks[0].get("text", "")
        logger.info("Single chunk, no merging needed")
        return text

    merged_text = transcript_chunks[0].get("text", "")
    logger.info(f"Starting merge with first chunk: {len(merged_text)} chars")

    for i in range(1, len(transcript_chunks)):
        current_text = transcript_chunks[i].get("text", "")

        # Find overlap using longest common sequence
        overlap_len = find_overlap(merged_text, current_text)

        if overlap_len > 0:
            # Remove overlap from current chunk and append
            merged_text += current_text[overlap_len:]
            logger.info(f"Chunk {i}: Found overlap ({overlap_len} chars), merged to {len(merged_text)} total chars")
        else:
            # No overlap found, append with space
            merged_text += " " + current_text
            logger.info(f"Chunk {i}: No overlap detected, appended with space")

    logger.info(f"Merge complete: {len(merged_text)} chars total")
    return merged_text


def transcribe_with_groq_chunked(
    audio_path: Path,
    episode_id: str,
) -> Optional[str]:
    """
    Transcribe large audio file by chunking and merging.

    Args:
        audio_path: Path to downloaded audio file
        episode_id: Episode ID for logging

    Returns:
        Merged transcript as JSON string or None
    """
    logger.info(f"Chunking and transcribing large file: {episode_id}")

    try:
        from groq import Groq
    except ImportError:
        logger.error("groq package not installed")
        return None

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY not set")
        return None

    # Create chunks (10-min with 10-sec overlap)
    try:
        chunk_paths = chunk_audio(audio_path)
    except Exception as e:
        logger.error(f"Failed to chunk audio for {episode_id}: {e}")
        return None

    if not chunk_paths:
        logger.error(f"No chunks created for {episode_id}")
        return None

    logger.info(f"Created {len(chunk_paths)} chunks for {episode_id}")

    # Transcribe each chunk
    client = Groq(api_key=api_key)
    transcripts = []

    for i, chunk_path in enumerate(chunk_paths):
        logger.info(f"Transcribing chunk {i + 1}/{len(chunk_paths)} for {episode_id}")

        try:
            with open(chunk_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            if hasattr(transcription, "model_dump"):
                transcripts.append(transcription.model_dump())
            else:
                transcripts.append({"text": transcription.text})

            logger.info(f"Chunk {i + 1} transcribed: {len(transcripts[-1].get('text', ''))} chars")

        except Exception as e:
            logger.error(f"Failed to transcribe chunk {i} for {episode_id}: {e}")
            # Clean up chunks and fail
            for p in chunk_paths:
                try:
                    p.unlink(missing_ok=True)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up chunk {p}: {cleanup_error}")
            return None
        finally:
            # Clean up chunk file
            try:
                chunk_path.unlink(missing_ok=True)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up chunk {chunk_path}: {cleanup_error}")

    # Merge transcripts
    merged_text = merge_transcripts(transcripts)

    # Create combined output matching Groq format
    combined_output = {
        "text": merged_text,
        "chunks": len(chunk_paths),
        "duration": sum(t.get("duration", 0) for t in transcripts),
        "segments": [],  # Could combine segments if needed
    }

    logger.info(f"Merged {len(chunk_paths)} chunks for {episode_id}")

    return json.dumps(combined_output, ensure_ascii=False, indent=2)


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
