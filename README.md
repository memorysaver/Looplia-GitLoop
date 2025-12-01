# Looplia-GitLoop

An AI-powered content archival system that automatically collects metadata from multiple sources and on-demand downloads full content materials for writing, powered by GitHub Actions and Groq's Whisper API for transcription.

## Features

- **Dual-Phase Architecture**: Automatically archive metadata hourly, then manually download full content when needed
- **Multi-Source Support**: YouTube channels, podcasts (RSS & Apple Podcasts), blogs, and news aggregators
- **Smart Transcription**: Groq Whisper API for podcast audio transcription with automatic chunking for large files
- **YouTube Captions**: Extract captions and transcripts from videos
- **Clean Article Extraction**: Convert web content to markdown for easy reading
- **Modular Architecture**: Easy to extend with new content sources following existing patterns
- **Persistent Caching**: Smart storage system to avoid redundant downloads and processing
- **Hourly Automation**: Archive workflows run automatically on a schedule; material workflows are on-demand

## How It Works

The system operates in two distinct phases:

**Phase 1 - Archive (Automatic, Hourly)**
- Runs automatically every hour to fetch metadata from your subscriptions
- Saves metadata (titles, links, publish dates, etc.) to `subscriptions/` directory
- Fast operation - keeps only essential information
- Examples: YouTube video titles, podcast episode names, article headlines

**Phase 2 - Materials (Manual, On-Demand)**
- Triggered manually when you need full content for writing
- Downloads complete content: transcripts, captions, article text
- Saves to `writing-materials/` directory
- Examples: Full transcripts from podcasts and YouTube, cleaned article markdown

This separation allows automatic metadata collection without overwhelming storage or API limits, while enabling comprehensive content extraction when you actively need materials for writing.

## Project Structure

```
Looplia-GitLoop/
├── .github/workflows/                # GitHub Actions automation
│   ├── archive-youtube.yml           # Automatic YouTube metadata (hourly :00)
│   ├── archive-podcast.yml           # Automatic podcast metadata (hourly :15)
│   ├── archive-blog.yml              # Automatic blog metadata (hourly :30)
│   ├── archive-news.yml              # Automatic news metadata (hourly :45)
│   ├── material-youtube.yml          # Manual: YouTube caption/transcript download
│   ├── material-podcast.yml          # Manual: Podcast transcription (Groq API)
│   └── material-articles.yml         # Manual: Article content extraction
│
├── config/                           # Configuration by source type
│   ├── youtube/sources.json
│   ├── podcast/sources.json
│   ├── blog/sources.json
│   └── news/sources.json
│
├── scripts/
│   ├── core/                         # Base framework
│   │   ├── archiver_base.py         # Base class for all archivers
│   │   ├── base_handler.py          # Base class for all handlers
│   │   └── utils.py                 # Shared utilities
│   ├── youtube/
│   │   ├── archiver.py
│   │   └── handler.py
│   ├── podcast/
│   │   ├── archiver.py
│   │   └── handler.py
│   ├── blog/
│   ├── news/
│   ├── material_downloader.py        # Main orchestrator for material downloads
│   ├── youtube_material.py           # YouTube caption extraction
│   ├── podcast_material.py           # Podcast transcription (Groq)
│   └── article_material.py           # Article content extraction
│
├── subscriptions/                    # Archived metadata (automatic, hourly)
│   ├── youtube/{source-key}/
│   ├── podcast/{source-key}/
│   ├── blog/{source-key}/
│   └── news/{source-key}/
│
└── writing-materials/                # Full content (manual, on-demand)
    ├── youtube/{source-key}/
    ├── podcast/{source-key}/
    ├── blogs/{source-key}/
    └── news/{source-key}/
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r scripts/requirements.txt
```

### 2. Configure Sources
Edit configuration files for each source type you want to use:

```bash
# YouTube
nano config/youtube/sources.json

# Podcasts
nano config/podcast/sources.json

# Blogs
nano config/blog/sources.json

# News
nano config/news/sources.json
```

### 3. Enable GitHub Actions
Push to GitHub - archive workflows run automatically on a schedule (no setup needed).

### 4. (Optional) Set Up Podcast Transcription
For podcast transcription using Groq API:
1. Get a Groq API key from https://console.groq.com
2. Add `GROQ_API_KEY` to your GitHub repository secrets
3. Trigger `material-podcast.yml` workflow to start transcribing

## Configuration

Configuration files are organized by source type in `config/{type}/sources.json`.

### Configuration Format

Each source file follows this structure:

```json
{
  "version": "3.0.0",
  "type": "youtube",
  "metadata": {
    "description": "YouTube channel subscriptions",
    "requires_cookies": true,
    "requires_ytdlp": true,
    "runner": "self-hosted"
  },
  "sources": [
    {
      "key": "anthropic-ai",
      "name": "Anthropic AI",
      "type": "youtube",
      "url": "https://www.youtube.com/@anthropic-ai",
      "enabled": true,
      "options": {
        "extract_transcript": true,
        "transcript_languages": ["en"],
        "max_entries_per_run": 10
      }
    }
  ]
}
```

### Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `key` | string | Unique identifier for the source (used for file paths) |
| `name` | string | Human-readable name for the source |
| `type` | string | Source type: `youtube`, `podcast`, `blog`, `news` |
| `url` | string | Channel/feed URL |
| `enabled` | boolean | Enable/disable this source |
| `max_entries_per_run` | integer | Maximum entries to process per workflow run |
| `extract_transcript` | boolean | (YouTube) Extract video transcripts |
| `transcript_languages` | array | (YouTube) Preferred transcript languages |
| `use_ytdlp` | boolean | (Podcast) Use yt-dlp for enrichment |

### Example: Podcast Configuration
```json
{
  "key": "guigu101",
  "name": "矽谷101",
  "type": "podcast",
  "url": "https://podcasts.apple.com/tw/podcast/id1498541229",
  "enabled": true,
  "options": {
    "use_ytdlp": true,
    "max_entries_per_run": 10
  }
}
```

## GitHub Actions Workflows

### Archive Workflows (Automatic, Hourly)

These run automatically on a schedule to archive metadata:

| Workflow | Schedule | Metadata Archived |
|----------|----------|-------------------|
| `archive-youtube.yml` | Every hour at :00 | Video titles, URLs, metadata |
| `archive-podcast.yml` | Every hour at :15 | Episode names, URLs, published dates |
| `archive-blog.yml` | Every hour at :30 | Article titles, links, summaries |
| `archive-news.yml` | Every hour at :45 | News headlines, sources, URLs |

### Material Workflows (Manual Trigger Only)

These download full content on demand:

| Workflow | Purpose | Triggered Via |
|----------|---------|---------------|
| `material-youtube.yml` | Download video captions/transcripts | GitHub Actions UI |
| `material-podcast.yml` | Transcribe podcast audio (Groq API) | GitHub Actions UI |
| `material-articles.yml` | Extract article content to markdown | GitHub Actions UI |

### How to Trigger Material Downloads

1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select the workflow (e.g., `material-podcast.yml`)
4. Click **Run workflow**
5. (Optional) Enter `source_key` to process only a specific source

## Usage

### Via GitHub Actions (Recommended)

**Archive workflows** run automatically - you don't need to do anything. Metadata is collected hourly.

**Material workflows** require manual triggering:
1. Go to Actions tab
2. Select workflow (`material-youtube.yml`, `material-podcast.yml`, or `material-articles.yml`)
3. Click **Run workflow**
4. (Optional) Specify `source_key` parameter to process only one source

### Local Development

Install requirements first:
```bash
pip install -r scripts/requirements.txt
```

**Archive a specific source:**
```bash
# Archive YouTube source
SOURCE_TYPE=youtube SOURCE_KEY=anthropic-ai python -m youtube.archiver

# Archive podcast source
SOURCE_TYPE=podcast SOURCE_KEY=guigu101 python -m podcast.archiver

# Force reprocess (skip duplicate detection)
FORCE_REPROCESS=true SOURCE_TYPE=youtube SOURCE_KEY=anthropic-ai python -m youtube.archiver
```

**Download materials:**
```bash
# Download YouTube captions
SOURCE_TYPE=youtube SOURCE_KEY=anthropic-ai python youtube_material.py

# Transcribe podcasts (requires GROQ_API_KEY)
SOURCE_TYPE=podcast SOURCE_KEY=guigu101 python podcast_material.py

# Extract article content
SOURCE_TYPE=blog SOURCE_KEY=medium python article_material.py
```

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `SOURCE_TYPE` | Filter by content type | `youtube`, `podcast`, `blog`, `news` |
| `SOURCE_KEY` | Filter by specific source | `anthropic-ai`, `guigu101` |
| `FORCE_REPROCESS` | Re-archive already archived entries | `true` |
| `GROQ_API_KEY` | API key for Groq transcription | (from https://console.groq.com) |
| `YT_COOKIES_FROM_BROWSER` | Browser for YouTube cookies | `chrome`, `firefox` (self-hosted only) |

## Data Storage

### Subscriptions Directory (`subscriptions/`)

Stores metadata from automatic archiving. Files are git-tracked and kept small.

**Structure:**
```
subscriptions/
└── youtube/
    └── anthropic-ai/
        ├── index.json          # Summary with all archived entries
        └── {video-id}.json     # Individual entry metadata
```

**Index Example:**
```json
{
  "source_key": "anthropic-ai",
  "source_name": "Anthropic AI",
  "source_type": "youtube",
  "source_url": "https://www.youtube.com/@anthropic-ai",
  "last_updated": "2024-01-15T10:30:00Z",
  "total_entries": 5,
  "entries": [
    {
      "id": "dQw4w9WgXcQ",
      "title": "Video Title",
      "published": "2024-01-15T08:00:00Z",
      "file": "dQw4w9WgXcQ.json"
    }
  ]
}
```

### Writing Materials Directory (`writing-materials/`)

Stores full content from manual downloads. Files are git-tracked.

**YouTube Example:**
```
writing-materials/
└── youtube/
    └── anthropic-ai/
        ├── dQw4w9WgXcQ.md       # Markdown with transcript
        └── dQw4w9WgXcQ.vtt      # Raw VTT captions
```

**Podcast Example:**
```
writing-materials/
└── podcast/
    └── guigu101/
        ├── episode-1.md               # Groq-transcribed content
        └── episode-1.whisper.json     # Raw Groq API response
```

**Article Example:**
```
writing-materials/
└── blogs/
    └── medium/
        └── article-slug.md            # Cleaned article markdown
```

## For Contributors

Looplia-GitLoop uses a modular architecture that makes it easy to add new content sources.

### Architecture Overview

**Core Framework** (`scripts/core/`)
- `archiver_base.py`: Abstract base class defining the archiving workflow
- `base_handler.py`: Abstract base class defining content-specific handlers
- `utils.py`: Shared utility functions

**Source-Specific Packages** (`scripts/{type}/`)
Each source type has its own package with:
- `archiver.py`: Implements the archiving logic for that type
- `handler.py`: Implements content-specific fetching and parsing

### Adding a New Source Type

1. Create `scripts/{type}/` directory (e.g., `scripts/tiktok/`)
2. Create `archiver.py` extending `BaseArchiver`
3. Create `handler.py` extending `BaseSubscriptionHandler`
4. Create config file `config/{type}/sources.json`
5. (Optional) Create material downloader if full content extraction is needed

The modular design ensures consistency across all source types while allowing flexibility for type-specific features.

## Requirements

- Python 3.8+
- Git
- GitHub account with Actions enabled

### Python Dependencies

Key dependencies are automatically installed with `pip install -r scripts/requirements.txt`:

- `yt-dlp`: YouTube video downloading and metadata extraction
- `feedparser`: RSS feed parsing
- `groq`: Groq API client for podcast transcription
- `pydub`: Audio file processing (for podcast chunking)
- `trafilatura`: Web article content extraction
- `requests`: HTTP client library

### External Requirements

- **YouTube**: Self-hosted runner with browser cookies for authentication
- **Podcasts**: Groq API key (free tier available at https://console.groq.com)
- **Blogs/News**: No special requirements

## License

MIT
