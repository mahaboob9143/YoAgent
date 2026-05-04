"""
agents/youtube_scraper_agent.py — YouTubeScraperAgent for YoAgent.

Responsibilities:
  1. Scrape recent Shorts from configured YouTube source URL(s) using yt-dlp
     (flat extract only — no full download via yt-dlp to avoid CI bot blocks).
  2. Skip shorts already uploaded (dedup via reposted_ids.txt).
  3. Download the short .mp4 via the Cobalt.tools API (proxied — works on any IP).
  4. Fall back to direct yt-dlp download if Cobalt is unavailable (local dev).
  5. Return a result dict ready for YouTubeUploaderAgent.

Why Cobalt instead of yt-dlp for downloads?
  GitHub Actions runners use Microsoft Azure datacenter IPs that YouTube
  infrastructure-blocks for video downloads regardless of cookies or client
  spoofing.  Cobalt proxies the download through their own servers, so the
  runner IP is irrelevant.

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

import requests as _requests

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from core.repost_tracker import is_reposted as is_post_reposted, mark_reposted as log_repost
from core.flags import get_config
from core.logger import get_logger

logger = get_logger("YouTubeScraperAgent")

# ── Cobalt API ────────────────────────────────────────────────────────────────
# Cobalt is a free, open-source video-download proxy (https://cobalt.tools).
# Requests go to their servers, so the CI runner IP is never exposed to YouTube.
COBALT_TIMEOUT = 30          # seconds for the Cobalt API call
COBALT_DL_TIMEOUT = 180      # seconds for the actual video stream download

# YouTube Shorts max duration as of October 2024 — 3 minutes.
# Use 175 s as the cutoff to stay safely below the hard limit.
SHORTS_MAX_DURATION = 175


def _get_cookies_file() -> Optional[str]:
    """
    Return the path to a Netscape-format cookies.txt file for yt-dlp, or None.

    Used only for the flat-extract (metadata listing) step — NOT for downloads,
    which now go through Cobalt.

    Resolution order:
      1. YOUTUBE_COOKIES_FILE env var (set by the GitHub Actions workflow after
         decoding the YOUTUBE_COOKIES_B64 secret).
      2. A 'cookies.txt' file in the current working directory (local dev fallback).
    """
    env_path = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
    if env_path and os.path.isfile(env_path):
        logger.info(f"Using YouTube cookies file for flat-extract: {env_path}")
        return env_path

    local_path = "cookies.txt"
    if os.path.isfile(local_path):
        logger.info(f"Using local cookies file for flat-extract: {local_path}")
        return os.path.abspath(local_path)

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
        """Scrape a YouTube channel URL for unseen Shorts using yt-dlp flat extract."""
        logger.info(f"Scraping {url} — looking for an unseen SHORT...")

        cookies_file = _get_cookies_file()
        ydl_opts_flat = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "playlistend": max_check,
            **( {"cookiefile": cookies_file} if cookies_file else {} ),
        }

        video_candidates = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
                info = ydl.extract_info(url, download=False)
                if "entries" in info:
                    video_candidates = list(info["entries"])
                else:
                    video_candidates = [info]
        except Exception as exc:
            logger.error(f"Failed to fetch video list from {url}: {exc}")
            return None

        if not video_candidates:
            logger.warning(f"No videos found at {url}")
            return None

        logger.info(f"Found {len(video_candidates)} recent videos. Scanning for unseen...")

        # Shuffle so we don't always pick the newest video
        random.shuffle(video_candidates)

        last_valid_info: Optional[Dict] = None  # fallback if entire pool is already uploaded
        for video_info in video_candidates:
            if not video_info:
                continue

            video_id = video_info.get("id")
            if not video_id:
                continue

            # Duration check using flat-entry data (avoids a full yt-dlp extract)
            duration = video_info.get("duration") or 0
            if duration and duration > SHORTS_MAX_DURATION:
                logger.info(
                    f"Skipping {video_id} — duration {duration}s "
                    f"(exceeds Shorts max of {SHORTS_MAX_DURATION}s)"
                )
                log_repost(video_id)   # never check this one again
                continue

            # Track for fallback
            last_valid_info = video_info

            # Dedup
            if is_post_reposted(video_id):
                logger.debug(f"Already uploaded YT ID {video_id} — skipping")
                continue

            # Polite delay before download
            rl = self.config.get("rate_limits", {})
            delay = random.uniform(
                float(rl.get("yt_pre_download_min", 3)),
                float(rl.get("yt_pre_download_max", 9)),
            )
            logger.info(f"Rate-limit: sleeping {delay:.1f}s before download...")
            time.sleep(delay)

            result = self._download_video(
                video_id=video_id,
                video_info=video_info,
                download_dir=download_dir,
            )
            if result:
                return result

        # ── Fallback: entire pool was already uploaded ────────────────────────
        # Repost the last valid candidate so the channel never goes silent.
        if last_valid_info:
            fallback_id = last_valid_info.get("id", "")
            logger.warning(
                f"All {len(video_candidates)} recent videos already uploaded. "
                f"Falling back to repost last candidate: {fallback_id}"
            )
            rl = self.config.get("rate_limits", {})
            delay = random.uniform(
                float(rl.get("yt_pre_download_min", 3)),
                float(rl.get("yt_pre_download_max", 9)),
            )
            logger.info(f"Rate-limit: sleeping {delay:.1f}s before fallback download...")
            time.sleep(delay)
            return self._download_video(
                video_id=fallback_id,
                video_info=last_valid_info,
                download_dir=download_dir,
            )

        logger.info(f"All recent videos from {url} have already been uploaded.")
        return None

    # ── Download ──────────────────────────────────────────────────────────────

    def _download_video(
        self,
        video_id: str,
        video_info: Dict[str, Any],
        download_dir: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Download the video using the backend configured in config.yaml.

        use_cobalt: true  → Cobalt.tools API first, yt-dlp as fallback
        use_cobalt: false → yt-dlp only (original behaviour, works locally)

        Metadata (title, description, uploader) is taken from the flat-extract
        video_info dict so no extra yt-dlp call is needed.
        """
        yt_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"Downloading Short: {yt_url}")

        local_path = os.path.join(download_dir, f"yt_{video_id}.mp4")
        yt_cfg = self.config.get("youtube_scraper", {})
        use_cobalt = yt_cfg.get("use_cobalt", True)

        success = False

        if use_cobalt:
            # ── Primary: Cobalt.tools (CI-safe, proxied) ─────────────────────
            logger.info("Downloader: Cobalt.tools (use_cobalt=true)")
            success = self._download_via_cobalt(yt_url, local_path)
            if not success:
                logger.warning("Cobalt failed — falling back to yt-dlp...")
                success = self._download_via_ytdlp(video_id, download_dir, local_path)
        else:
            # ── Primary: yt-dlp (original, works on residential IPs) ─────────
            logger.info("Downloader: yt-dlp (use_cobalt=false)")
            success = self._download_via_ytdlp(video_id, download_dir, local_path)

        if not success or not os.path.exists(local_path):
            logger.error(f"All download methods failed for {video_id}.")
            return None

        file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
        logger.info(f"Downloaded: yt_{video_id}.mp4 ({file_size_mb:.1f} MB)")

        # Mark as uploaded so we never re-download
        log_repost(video_id)

        # Build caption from flat-entry metadata
        title       = video_info.get("title", "")
        description = video_info.get("description", "") or ""
        uploader    = video_info.get("uploader", "") or video_info.get("channel", "Unknown Channel")

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

    # ── Cobalt downloader ─────────────────────────────────────────────────────

    # Known public cobalt-compatible instances (tried in order).
    # The official api.cobalt.tools sometimes disables YouTube — fallbacks ensure resilience.
    _COBALT_INSTANCES = [
        "https://api.cobalt.tools/",
        "https://cobalt.api.timelessnesses.me/",
        "https://cobalt.api.lostfound.stream/",
    ]

    def _download_via_cobalt(self, yt_url: str, local_path: str) -> bool:
        """
        Download a YouTube video via the Cobalt.tools API.

        Cobalt proxies the download through their servers, bypassing YouTube's
        IP-based bot detection that blocks GitHub Actions datacenter IPs.

        Tries multiple known public Cobalt instances in order.
        Returns True on success, False if all instances fail.
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # Correct Cobalt API field names: vQuality (not videoQuality)
        # Sends minimal payload first; the url field is the only required one.
        payload = {
            "url": yt_url,
            "vQuality": "720",
            "vCodec": "h264",
        }

        for instance_url in self._COBALT_INSTANCES:
            try:
                logger.info(f"Cobalt: trying {instance_url} for {yt_url} ...")
                resp = _requests.post(
                    instance_url,
                    json=payload,
                    headers=headers,
                    timeout=COBALT_TIMEOUT,
                )

                # On 400, retry with the bare-minimum payload (just url)
                # — some instances reject optional fields they don't recognise.
                if resp.status_code == 400:
                    logger.debug("Cobalt 400 — retrying with minimal payload...")
                    resp = _requests.post(
                        instance_url,
                        json={"url": yt_url},
                        headers=headers,
                        timeout=COBALT_TIMEOUT,
                    )

                resp.raise_for_status()
                data = resp.json()

                status = data.get("status", "")
                if status == "error":
                    err = data.get("error", {})
                    logger.warning(
                        f"Cobalt ({instance_url}) returned error: "
                        f"{err.get('code', 'unknown')} — {err}"
                    )
                    continue  # try next instance

                download_url = data.get("url")
                if not download_url:
                    logger.warning(
                        f"Cobalt ({instance_url}) returned status '{status}' "
                        "but no download URL — skipping."
                    )
                    continue

                logger.info(f"Cobalt returned '{status}' — streaming to disk...")
                with _requests.get(download_url, stream=True, timeout=COBALT_DL_TIMEOUT) as stream:
                    stream.raise_for_status()
                    with open(local_path, "wb") as f:
                        for chunk in stream.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)

                if os.path.getsize(local_path) < 1024:
                    logger.warning("Cobalt produced an empty/near-empty file — skipping.")
                    os.remove(local_path)
                    continue

                logger.info(f"Cobalt download successful via {instance_url}")
                return True

            except Exception as exc:
                logger.warning(f"Cobalt instance {instance_url} failed: {exc}")
                if os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
                continue  # try next instance

        logger.warning("All Cobalt instances failed.")
        return False

    # ── yt-dlp fallback downloader ────────────────────────────────────────────

    def _download_via_ytdlp(self, video_id: str, download_dir: str, local_path: str) -> bool:
        """
        Download via yt-dlp (works on local machines, blocked on GitHub Actions CI).
        Returns True on success, False on failure.
        """
        if yt_dlp is None:
            return False

        yt_url = f"https://www.youtube.com/watch?v={video_id}"
        filename_template = os.path.join(download_dir, f"yt_{video_id}.%(ext)s")
        cookies_file = _get_cookies_file()

        ydl_opts = {
            "format": "b[ext=mp4]/best",
            "outtmpl": filename_template,
            "quiet": True,
            "no_warnings": True,
            **( {"cookiefile": cookies_file} if cookies_file else {} ),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(yt_url, download=True)
                ytdlp_path = ydl.prepare_filename(info)
                # yt-dlp may use a different extension — rename to .mp4 for consistency
                if ytdlp_path != local_path and os.path.exists(ytdlp_path):
                    os.rename(ytdlp_path, local_path)
            return os.path.exists(local_path)
        except Exception as exc:
            logger.warning(f"yt-dlp download failed for {video_id}: {exc}")
            return False
