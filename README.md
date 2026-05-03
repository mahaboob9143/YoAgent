# YoAgent — YouTube Shorts Automation Pipeline

A fully autonomous agent that scrapes short-form Islamic content from public sources (Instagram Reels or YouTube Shorts) and uploads them to your YouTube channel as Shorts — running for free on **GitHub Actions**.

## Features

- **Dual-Source Scraping:** Configurable to scrape from either Instagram (via `instaloader`) or YouTube (via `yt-dlp`).
- **Auto-Generated Metadata:** Rule-based engine generates a YouTube title, description, and tags from the original caption — zero AI cost.
- **Direct Upload:** Uses the YouTube Data API v3 resumable upload — chunk-safe for large videos, no intermediate hosting.
- **Robust Deduplication:** In-memory cached flat-file tracker ensures `O(1)` performance and guarantees no video is ever uploaded twice.
- **Polite Scraping & Rate Limits:** Randomized, human-like delays built into iterations and downloads to evade bot detection and prevent IP bans/session invalidations.
- **Resilience:** Built-in exponential backoff retry loops for network drops or API hiccups during both downloading and uploading.
- **Content Filters:** Built-in Jummah (Friday) and Ramadan content awareness.
- **Headless CI/CD:** Designed to run on GitHub Actions twice daily with randomized start-time jitter for maximum stealth.

## Local Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure credentials
```bash
cp .env.template .env
# Fill in IG_SCRAPE_USER, IG_SESSION_ID (if using Instagram as a source)
```

### 3. Set up YouTube OAuth2 (one-time)
```bash
python scripts/get_youtube_token.py
# Follow the browser prompt, then copy the printed YOUTUBE_REFRESH_TOKEN into .env
```

### 4. Configuration
Edit `config.yaml` to choose your source (`scrape_source: youtube` or `scrape_source: instagram`), define source accounts/URLs, and adjust rate limits.

### 5. Run the pipeline
```bash
python main.py --repost           # Scrape a video and upload to YouTube Shorts
python main.py --repost --dry-run # Test without actually downloading or uploading
```

## Cloud Deployment
See [DEPLOYMENT.md](DEPLOYMENT.md) for full GitHub Actions setup instructions.
