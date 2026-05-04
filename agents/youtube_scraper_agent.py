"""
agents/youtube_scraper_agent.py — YouTubeScraperAgent for YoAgent.

Responsibilities:
  1. Scrape recent Shorts from configured YouTube source URL(s) using yt-dlp.
  2. Skip shorts already uploaded (dedup via reposted_ids.txt).
  3. Download the short .mp4 to media/reposts/.
  4. Return a result dict ready for YouTubeUploaderAgent.

Usage:
    agent = YouTubeScraperAgent()
    result = agent.run()
    if result:
        # result["video"]            — video dict with local_path
        # result["original_caption"] — raw YT title + description for metadata engine
        # result["source_post_id"]   — YouTube video ID (for dedup)
"""

import os
import random
import time
from typing import Optional, Dict, Any

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from core.repost_tracker import is_reposted as is_post_reposted, mark_reposted as log_repost
from core.flags import get_config
from core.logger import get_logger

logger = get_logger("YouTubeScraperAgent")


def _get_cookies_file() -> Optional[str]:
    """
    Return the path to a Netscape-format cookies.txt file for yt-dlp, or None.

    Resolution order:
      1. YOUTUBE_COOKIES_FILE env var (set by the GitHub Actions workflow after
         decoding the YOUTUBE_COOKIES_B64 secret).
      2. A 'cookies.txt' file in the current working directory (local dev fallback).
    """
    env_path = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
    if env_path and os.path.isfile(env_path):
        logger.info(f"Using YouTube cookies file: {env_path}")
        return env_path

    local_path = "cookies.txt"
    if os.path.isfile(local_path):
        logger.info(f"Using local cookies file: {local_path}")
        return os.path.abspath(local_path)

    logger.warning(
        "No YouTube cookies file found. "
        "Downloads may fail on CI runners. "
        "Set YOUTUBE_COOKIES_B64 in GitHub Secrets — see DEPLOYMENT.md."
    )
    return None


class YouTubeScraperAgent:
    """Scrapes Shorts from a YouTube channel for reposting."""

    def __init__(self):
        self.config = get_config()
        if yt_dlp is None:
            logger.error("yt-dlp is not installed. Run: pip install yt-dlp")

    # ── Public entry point ───────────────────────────────────────────────────

    def run(self) -> Optional[Dict[str, Any]]:
        """
        Main entry point. Finds one unseen Short from the configured source URLs
        and returns a result dict ready for YouTubeUploaderAgent, or None if nothing found.
        """
        if yt_dlp is None:
            return None

        self.config = get_config()
        yt_cfg = self.config.get("youtube_scraper", {})
        
        source_urls  = yt_cfg.get("source_urls", [])
        max_check    = int(yt_cfg.get("max_videos_to_check", 20))
        download_dir = yt_cfg.get("download_dir", "media/reposts")
        add_credit   = yt_cfg.get("add_credit_line", True)

        os.makedirs(download_dir, exist_ok=True)

        if not source_urls:
            logger.warning("No source_urls configured in config.yaml under youtube_scraper.")
            return None

        for url in source_urls:
            result = self._process_channel(
                url=url,
                max_check=max_check,
                download_dir=download_dir,
                add_credit=add_credit,
            )
            if result:
                return result

        logger.warning("No new unseen Shorts found across all source URLs.")
        return None

    # ── Scraping ─────────────────────────────────────────────────────────────

    def _process_channel(
        self,
        url: str,
        max_check: int,
        download_dir: str,
        add_credit: bool,
    ) -> Optional[Dict[str, Any]]:
        """Scrape a YouTube channel URL for unseen Shorts."""
        logger.info(f"Scraping {url} — looking for an unseen SHORT...")

        cookies_file = _get_cookies_file()
        ydl_opts_flat = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
            'playlistend': max_check,  # Only fetch up to max_check items
            **({'cookiefile': cookies_file} if cookies_file else {}),
        }

        video_candidates = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    video_candidates = list(info['entries'])
                else:
                    video_candidates = [info]
        except Exception as exc:
            logger.error(f"Failed to fetch videos from {url}: {exc}")
            return None

        if not video_candidates:
            logger.warning(f"No videos found at {url}")
            return None
            
        logger.info(f"Found {len(video_candidates)} recent videos. Scanning for unseen...")

        # Optional: shuffle to mix it up, or keep chronological
        random.shuffle(video_candidates)

        last_valid_id: Optional[str] = None  # fallback if entire pool is already uploaded
        for video_info in video_candidates:
            if not video_info:
                continue
                
            video_id = video_info.get('id')
            if not video_id:
                continue

            # Track the last valid candidate as a forced fallback in case the
            # entire pool turns out to be already uploaded (see end of loop).
            last_valid_id = video_id

            # Dedup
            if is_post_reposted(video_id):
                logger.debug(f"Already uploaded YT ID {video_id} — skipping")
                continue

            # Polite delay before download (configurable via config.yaml rate_limits)
            rl = self.config.get("rate_limits", {})
            delay = random.uniform(
                float(rl.get("yt_pre_download_min", 3)),
                float(rl.get("yt_pre_download_max", 9)),
            )
            logger.info(f"Rate-limit: sleeping {delay:.1f}s before download...")
            time.sleep(delay)

            # Fetch full info and download
            result = self._download_video(
                video_id=video_id,
                channel_url=url,
                download_dir=download_dir,
                add_credit=add_credit,
            )
            if result:
                return result

        # ── Fallback: entire pool was already uploaded ────────────────────────
        # Rather than returning nothing and silently skipping the run, repost
        # the last valid candidate so the channel always gets fresh content.
        if last_valid_id:
            logger.warning(
                f"All {len(video_candidates)} recent videos already uploaded. "
                f"Falling back to repost last candidate: {last_valid_id}"
            )
            rl = self.config.get("rate_limits", {})
            delay = random.uniform(
                float(rl.get("yt_pre_download_min", 3)),
                float(rl.get("yt_pre_download_max", 9)),
            )
            logger.info(f"Rate-limit: sleeping {delay:.1f}s before fallback download...")
            time.sleep(delay)
            return self._download_video(
                video_id=last_valid_id,
                channel_url=url,
                download_dir=download_dir,
                add_credit=add_credit,
            )

        logger.info(f"All recent videos from {url} have already been uploaded.")
        return None

    # ── Download ──────────────────────────────────────────────────────────────

    def _download_video(
        self,
        video_id: str,
        channel_url: str,
        download_dir: str,
        add_credit: bool,
    ) -> Optional[Dict[str, Any]]:
        """Download the actual video using yt-dlp with up to 3 retry attempts."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"Downloading unseen Short: {url} ...")

        filename_template = os.path.join(download_dir, f"yt_{video_id}.%(ext)s")

        cookies_file = _get_cookies_file()
        ydl_opts = {
            'format': 'b[ext=mp4]/best',   # best pre-merged mp4 (no ffmpeg required)
            'outtmpl': filename_template,
            'quiet': True,
            'no_warnings': True,
            **({'cookiefile': cookies_file} if cookies_file else {}),
        }

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                    # Verify duration — skip if not actually a Short.
                    # YouTube Shorts max is 3 minutes (180 s) as of October 2024.
                    # Use 175 s as the cutoff to allow a small encoding/metadata buffer.
                    duration = info.get('duration', 0)
                    if duration > 175:
                        logger.info(
                            f"Skipping {video_id} — duration {duration}s (too long for a Short)"
                        )
                        # Mark so we never re-download this in future runs
                        log_repost(video_id)
                        return None

                    local_path = ydl.prepare_filename(info)

                    if not os.path.exists(local_path):
                        raise FileNotFoundError(
                            f"File not found after download: {local_path}"
                        )

                    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
                    logger.info(f"Downloaded: yt_{video_id}.mp4 ({file_size_mb:.1f} MB)")

                    # Mark as uploaded so we never re-download it
                    log_repost(video_id)

                    title       = info.get('title', '')
                    description = info.get('description', '')
                    uploader    = info.get('uploader', 'Unknown Channel')

                    original_caption = title
                    if description:
                        original_caption += f"\n\n{description}"

                    video_dict = {
                        "id":             f"yt_{video_id}",
                        "local_path":     local_path,
                        "is_video":       True,
                        "source_post_id": video_id,
                        "_cleanup_path":  local_path,
                        "uploader":       uploader,
                    }

                    return {
                        "video":            video_dict,
                        "original_caption": original_caption,
                        "source_post_id":   video_id,
                    }

            except Exception as exc:
                if attempt < max_attempts:
                    wait = 10 * attempt  # 10s, 20s
                    logger.warning(
                        f"Download attempt {attempt}/{max_attempts} failed for {video_id}: "
                        f"{exc}. Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"Failed to download YT video {video_id} after {max_attempts} attempts: {exc}",
                        exc_info=True,
                    )
                    return None
