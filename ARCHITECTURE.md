# YoAgent — YouTube Shorts Architecture

A serverless, cloud-native pipeline for autonomous YouTube Shorts publishing, running on **GitHub Actions** for $0/month.

---

## 🏗 Core Infrastructure

### 1. Cloud-Native Hosting (GitHub Actions)
The entire system runs as a stateless container on GitHub-hosted runners, triggered twice daily via cron.
- **Workflow**: `.github/workflows/repost.yml`
- **Persistence**: The dedup tracker `data/reposted_ids.txt` is committed back to the repo after every successful run, keeping state across ephemeral runners.

### 2. Direct YouTube Upload
Unlike the previous Instagram pipeline, no intermediate image/video hosting is required.
The YouTube Data API v3 supports **resumable direct uploads** — the `.mp4` is streamed from the runner straight to YouTube in 10 MB chunks.

### 3. Rule-Based Metadata Engine (`core/youtube_metadata_engine.py`)
No LLM or external API needed. The engine:
- **Cleans** the original Instagram caption (strips hashtags, normalizes whitespace)
- **Classifies** it into one of 6 Islamic categories via keyword scoring: `sabr | shukr | tawakkul | akhirah | dua | general`
- **Assembles** a YouTube-optimized: `Title + Description + Tags`

---

## 🤖 The Core Agents

### 1. RepostAgent (`agents/repost_agent.py`)
- Scrapes Reels from public Islamic Instagram accounts using **Instaloader**.
- Authenticates via session cookie (no login challenge required).
- Applies content filters: skips Jummah posts on non-Fridays, skips Ramadan content when `is_ramadan=false`.
- Cross-references `reposted_ids.txt` to ensure 100% unique content.
- Downloads the `.mp4` to `media/reposts/` and returns the raw original caption.

### 2. YouTubeUploaderAgent (`agents/youtube_uploader_agent.py`)
- Authenticates via **OAuth2 refresh token** (stored as GitHub Secret — no browser needed in CI).
- Uploads the video using the **resumable upload protocol** (chunk-safe, handles large files).
- Sets title, description, tags, category, and privacy from the metadata engine output.
- Supports `--dry-run` mode — logs intent without calling the API.

### 3. Orchestrator (`agents/orchestrator.py`)
- Connects RepostAgent → YouTubeMetadataEngine → YouTubeUploaderAgent.
- Handles local `.mp4` cleanup after upload.

---

## 🔑 Key Files

| File | Purpose |
|---|---|
| `main.py` | Entry point — `python main.py --repost` |
| `config.yaml` | Runtime settings: source accounts, YouTube privacy, etc. |
| `core/youtube_metadata_engine.py` | Rule-based title/description/tag generator |
| `core/repost_tracker.py` | Flat-file dedup tracker |
| `data/reposted_ids.txt` | The "Stateless Database" — one shortcode per line |
| `scripts/get_youtube_token.py` | One-time local OAuth2 flow to get refresh token |
