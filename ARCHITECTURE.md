# InstaAgent — Serverless Repost Architecture

A streamlined, cloud-native automation pipeline for Instagram reposting, optimized for running on **GitHub Actions** for $0/month.

---

## 🏗 Core Infrastructure

### 1. Cloud-Native Hosting (GitHub Actions)
The entire system runs as a stateless container on GitHub-hosted runners. It is triggered twice daily via cron scheduling.
- **Workflow**: `.github/workflows/repost.yml`
- **Persistence**: Since GitHub runners are ephemeral, the system maintains its deduplication state by committing `data/reposted_ids.txt` back to the repository after every successful run.

### 2. Public Image Proxy (Cloudinary)
Meta's Graph API requires a publicly reachable URL to download images.
- **Implementation**: The `PosterAgent` uploads the scraped image to **Cloudinary** (configured via GitHub Secrets) to get a stable public URL.
- **Automatic Cleanup**: Immediately after the Meta API publishes the post, the script triggers a deletion request to Cloudinary to keep your storage usage at $0.

### 3. Rule-Based Captioning (`core/caption_engine.py`)
No LLM or Ollama is required. The system uses a bilingual (EN/AR) rule-based engine:
- **Scoring**: It classifies the original caption into spiritual categories (Sabr, Shukr, Tawakkul, etc.).
- **Assembling**: It stitches together a high-engagement structure: `[HOOK] + [BODY] + [CTA] + [HASHTAGS]`.

---

## 🤖 The Core Agents

### 1. RepostAgent (`agents/repost_agent.py`)
- Scrapes the latest content from public Islamic "Competitor" accounts.
- Uses **Instaloader** (no-login required for public profiles).
- Validates aspect ratios to ensure Meta's API won't reject the image.
- Cross-references the `reposted_ids.txt` tracker to ensure 100% unique content.

### 2. PosterAgent (`agents/poster_agent.py`)
- Executes the official **Meta Graph API 3-step publishing flow**:
  1. Uploads to Cloudinary.
  2. Creates a Media Container on Instagram.
  3. Polls status until `FINISHED`, then publishes.
- Automatically cleans up local temporary files and Cloudinary assets.

### 3. Orchestrator (`agents/orchestrator.py`)
- The simplified controller that connects the `RepostAgent` and `PosterAgent`.
- Handles error isolation and logging.

---

## 🔑 Key Files
- `main.py`: Entry point (`python main.py --repost`).
- `config.yaml`: Minimal configuration for sources and caption templates.
- `requirements.txt`: Lightweight dependencies (no heavy LLM or local server libs).
- `data/reposted_ids.txt`: The "Stateless Database" for deduplication.
