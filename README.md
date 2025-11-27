# Looplia-GitLoop

An AI-powered GitHub Action that uses Claude Code to auto-generate articles, open PRs, and publish upon approval.

## Features

- **RSS Archiver**: Automatically fetches and archives content from YouTube channels, podcasts, and blogs
- **Metadata Extraction**: Extracts rich metadata including transcripts from YouTube videos
- **Auto-commit**: Automatically commits archived content to the repository
- **Hourly Schedule**: Runs every hour to keep content up-to-date

## Project Structure

```
Looplia-GitLoop/
├── .github/workflows/
│   └── rss-archiver.yml      # GitHub Action workflow
├── config/
│   └── sources.json          # RSS source configuration
├── scripts/
│   ├── archiver.py           # Main archiver script
│   ├── youtube_handler.py    # YouTube-specific logic
│   ├── feed_handler.py       # RSS/Atom handler
│   ├── utils.py              # Utility functions
│   └── requirements.txt      # Python dependencies
└── rss/
    └── {source-key}/         # Archived content per source
        ├── index.json        # Index of all entries
        └── {entry-id}.json   # Individual entry files
```

## Configuration

### Adding Sources

Edit `config/sources.json` to add new RSS sources:

```json
{
  "version": "1.0.0",
  "sources": [
    {
      "key": "my-channel",
      "name": "My YouTube Channel",
      "type": "youtube_channel",
      "url": "https://www.youtube.com/@channel-name",
      "enabled": true,
      "options": {
        "extract_transcript": true,
        "transcript_languages": ["en"],
        "max_entries_per_run": 10
      }
    },
    {
      "key": "my-podcast",
      "name": "My Podcast",
      "type": "podcast",
      "url": "https://example.com/podcast/feed.xml",
      "enabled": true
    },
    {
      "key": "my-blog",
      "name": "My Blog",
      "type": "blog",
      "url": "https://example.com/blog/feed.xml",
      "enabled": true
    }
  ]
}
```

### Source Types

| Type | Description |
|------|-------------|
| `youtube_channel` | YouTube channel (extracts metadata + transcripts) |
| `youtube_playlist` | YouTube playlist |
| `podcast` | Podcast RSS feed |
| `blog` | Blog RSS/Atom feed |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `extract_transcript` | boolean | `true` | Extract transcripts (YouTube only) |
| `transcript_languages` | array | `["en"]` | Preferred transcript languages |
| `max_entries_per_run` | integer | `10` | Max entries to process per run |

## Usage

### Automatic (GitHub Actions)

The archiver runs automatically every hour via GitHub Actions. You can also trigger it manually:

1. Go to **Actions** tab
2. Select **RSS Archiver** workflow
3. Click **Run workflow**
4. Optionally specify:
   - `source_key`: Process only a specific source
   - `force_reprocess`: Re-process already archived entries

### Local Development

```bash
# Install dependencies
pip install -r scripts/requirements.txt
pip install yt-dlp

# Run the archiver
cd scripts
python archiver.py

# Process a specific source
SOURCE_KEY=anthropic-ai python archiver.py

# Force reprocess
FORCE_REPROCESS=true python archiver.py
```

## Archived Data Format

### YouTube Entry

```json
{
  "id": "video-id",
  "source_type": "youtube",
  "url": "https://www.youtube.com/watch?v=video-id",
  "title": "Video Title",
  "description": "Full description...",
  "channel": "Channel Name",
  "duration": 300,
  "view_count": 10000,
  "published": "20240115",
  "transcript": {
    "available": true,
    "language": "en",
    "auto_generated": true
  },
  "archived_at": "2024-01-15T10:30:00Z"
}
```

### Podcast Entry

```json
{
  "id": "episode-id",
  "source_type": "podcast",
  "title": "Episode Title",
  "link": "https://podcast.example.com/episode",
  "published": "2024-01-15T08:00:00Z",
  "audio": {
    "url": "https://cdn.example.com/episode.mp3",
    "type": "audio/mpeg"
  },
  "archived_at": "2024-01-15T10:30:00Z"
}
```

## License

MIT
