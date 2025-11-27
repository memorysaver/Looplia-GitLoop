# Looplia-GitLoop

An AI-powered GitHub Action that uses Claude Code to auto-generate articles, open PRs, and publish upon approval.

## Features

- **Subscription Archiver**: Automatically fetches and archives content from YouTube, podcasts, blogs, and news aggregators
- **Metadata Extraction**: Extracts rich metadata including transcripts from YouTube videos
- **Hybrid Podcast Support**: RSS discovery + yt-dlp enrichment for Apple Podcasts
- **Auto-commit**: Automatically commits archived content to the repository
- **Hourly Schedule**: Runs every hour to keep content up-to-date

## Project Structure

```
Looplia-GitLoop/
├── .github/workflows/
│   └── rss-archiver.yml           # GitHub Action workflow
├── config/
│   └── sources.json               # Source configuration
├── scripts/
│   ├── archiver.py                # Main archiver script
│   ├── youtube_handler.py         # YouTube-specific logic
│   ├── podcast_handler.py         # Podcast handler (RSS + yt-dlp)
│   ├── feed_handler.py            # Blog/News RSS handler
│   ├── utils.py                   # Utility functions
│   └── requirements.txt           # Python dependencies
└── subscriptions/                 # Archived content by type
    ├── youtube/
    │   └── {channel-key}/
    ├── podcast/
    │   └── {podcast-key}/
    ├── blogs/
    │   └── {blog-key}/
    └── news/
        └── {source-key}/
```

## Configuration

### Adding Sources

Edit `config/sources.json` to add new sources:

```json
{
  "version": "2.0.0",
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
    },
    {
      "key": "guigu101",
      "name": "矽谷101",
      "type": "podcast",
      "url": "https://podcasts.apple.com/tw/podcast/%E7%A1%85%E8%B0%B7101/id1498541229",
      "enabled": true,
      "options": {
        "use_ytdlp": true,
        "max_entries_per_run": 10
      }
    },
    {
      "key": "hackernews",
      "name": "Hacker News",
      "type": "news",
      "url": "https://hackernewsrss.com/feed.xml",
      "enabled": true,
      "options": {
        "max_entries_per_run": 30
      }
    }
  ]
}
```

### Source Types

| Type | Folder | Handler | Description |
|------|--------|---------|-------------|
| `youtube` | `/youtube/` | YouTubeHandler | YouTube channels/playlists with transcript extraction |
| `podcast` | `/podcast/` | PodcastHandler | Apple Podcasts, Spotify, RSS feeds with yt-dlp enrichment |
| `blogs` | `/blogs/` | FeedHandler | Blog RSS/Atom feeds |
| `news` | `/news/` | FeedHandler | News aggregators (HackerNews, etc.) |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `extract_transcript` | boolean | `true` | Extract transcripts (YouTube only) |
| `transcript_languages` | array | `["en"]` | Preferred transcript languages |
| `use_ytdlp` | boolean | `false` | Use yt-dlp for podcast enrichment |
| `max_entries_per_run` | integer | `10` | Max entries to process per run |

## Usage

### Automatic (GitHub Actions)

The archiver runs automatically every hour via GitHub Actions. You can also trigger it manually:

1. Go to **Actions** tab
2. Select **Subscription Archiver** workflow
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
  "duration": "01:23:45",
  "enriched_via": "rss",
  "archived_at": "2024-01-15T10:30:00Z"
}
```

### News Entry (HackerNews)

```json
{
  "id": "entry-id",
  "source_type": "news",
  "title": "Article Title",
  "link": "https://example.com/article",
  "published": "2024-01-15T08:00:00Z",
  "domain": "example.com",
  "comments_url": "https://news.ycombinator.com/item?id=12345",
  "hn_id": "12345",
  "points": 150,
  "comments_count": 42,
  "archived_at": "2024-01-15T10:30:00Z"
}
```

## Self-Hosted Runner

This project uses a self-hosted GitHub Actions runner for:
- Bypassing YouTube bot detection
- Using local browser cookies for authentication

```bash
# Check runner status
cd ~/actions-runner && ./svc.sh status

# Start/stop runner
cd ~/actions-runner && ./svc.sh start
cd ~/actions-runner && ./svc.sh stop
```

## License

MIT
