"""
agents/repost_agent.py — RepostAgent for YoAgent (Instagram Reels source).

Responsibilities:
  1. Check the repost.enabled feature flag.
  2. Scrape recent Reels from configured PUBLIC source account(s)
     using instaloader. A session cookie is injected for authenticated
     access; falls back to username+password, then anonymous.
  3. Skip reels already uploaded (dedup via reposted_ids.txt).
  4. Apply content filters (Jummah / Ramadan keywords).
  5. Apply polite rate-limit delays between requests.
  6. Download the reel .mp4 to media/reposts/.
  7. Return a result dict ready for YouTubeUploaderAgent.

Usage:
    agent = RepostAgent()
    result = agent.run()
    if result:
        # result["video"]            — video dict with local_path
        # result["original_caption"] — raw IG caption for metadata engine
        # result["source_post_id"]   — Instagram shortcode (for dedup)
"""

import io
import os
import random
import time
from typing import Optional, Dict, Any

import requests

from core.repost_tracker import is_reposted as is_post_reposted, mark_reposted as log_repost
from core.flags import get_config
from core.logger import get_logger

logger = get_logger("RepostAgent")


class RepostAgent:
    """Scrapes Reels from a public Islamic Instagram account for YouTube Shorts upload."""

    def __init__(self):
        self.config = get_config()

    # ── Public entry point ───────────────────────────────────────────────────

    def run(self) -> Optional[Dict[str, Any]]:
        """
        Main entry point. Finds one unseen Reel from the configured source accounts
        and returns a result dict ready for YouTubeUploaderAgent, or None if nothing found.
        """
        self.config = get_config()
        repost_cfg = self.config.get("repost", {})

        if not repost_cfg.get("enabled", False):
            logger.warning(
                "repost.enabled=false — skipped "
                "(set repost.enabled: true in config.yaml)"
            )
            return None

        source_accounts = repost_cfg.get("source_accounts", ["softeningsayings"])
        max_check       = int(repost_cfg.get("max_posts_to_check", 20))
        download_dir    = repost_cfg.get("download_dir", "media/reposts")
        add_credit      = repost_cfg.get("add_credit_line", True)

        os.makedirs(download_dir, exist_ok=True)

        for username in source_accounts:
            result = self._process_account(
                username=username,
                max_check=max_check,
                download_dir=download_dir,
                add_credit=add_credit,
            )
            if result:
                return result

        logger.warning("No new unseen Reels found across all source accounts.")
        return None

    # ── Authentication ───────────────────────────────────────────────────────

    def _get_session_id(self) -> Optional[str]:
        """
        Retrieve a valid Instagram session ID from:
          1. IG_SESSION_ID env var (URL-decoded if %3A-encoded).
          2. .ig_session.json — the instagrapi session cache on disk.
        Returns None if neither is available.
        """
        from urllib.parse import unquote

        raw = os.getenv("IG_SESSION_ID", "")
        if raw:
            return unquote(raw)

        session_file = ".ig_session.json"
        if os.path.exists(session_file):
            try:
                import json
                with open(session_file) as f:
                    settings = json.load(f)
                sid = (settings.get("cookies") or {}).get("sessionid")
                if sid:
                    logger.info("Reusing sessionid from cached .ig_session.json")
                    return sid
            except Exception as e:
                logger.debug(f"Could not read .ig_session.json: {e}")

        return None

    def _get_loader(self):
        """
        Build an instaloader instance.
        Injects a session cookie if available so Instagram doesn't 403 us.
        Falls back to fresh user/pass login, then anonymous (may be rate-limited).
        """
        import instaloader

        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            post_metadata_txt_pattern="",
            quiet=True,
        )

        # Suppress instaloader's internal 403-retry print messages using
        # an in-memory buffer instead of opening a real file handle.
        L.context.log_file = io.StringIO()

        session_id = self._get_session_id()
        username   = os.getenv("IG_SCRAPE_USER", "")
        password   = os.getenv("IG_SCRAPE_PASS", "")

        if session_id and username:
            L.context._session.cookies.set("sessionid", session_id, domain=".instagram.com")
            L.context.username = username
            logger.info(f"Instaloader authenticated via session cookie (@{username})")
        elif username and password:
            logger.info(f"Logging in as @{username} (username + password)...")
            try:
                L.login(username, password)
                logger.info("Login successful.")
            except Exception as e:
                logger.warning(f"Login failed: {e} — trying anonymous access")
        else:
            logger.warning(
                "No Instagram credentials found — anonymous access may be rate-limited. "
                "Add IG_SCRAPE_USER + IG_SESSION_ID to .env"
            )

        return L

    # ── Scraping ─────────────────────────────────────────────────────────────

    def _process_account(
        self,
        username: str,
        max_check: int,
        download_dir: str,
        add_credit: bool,
    ) -> Optional[Dict[str, Any]]:
        """Scrape a public account for unseen Reels."""
        import instaloader

        logger.info(f"Scraping @{username} — looking for an unseen REEL...")

        try:
            L       = self._get_loader()
            profile = instaloader.Profile.from_username(L.context, username)
        except Exception as exc:
            logger.error(f"Failed to access profile @{username}: {exc}")
            return None

        logger.info(
            f"@{username}: {profile.mediacount} total posts — "
            f"scanning up to {max_check} for unseen Reels..."
        )

        # Collect reel candidates
        reel_candidates = []
        rl = self.config.get("rate_limits", {})
        iter_min = float(rl.get("ig_post_iter_min", 4))
        iter_max = float(rl.get("ig_post_iter_max", 10))

        try:
            for post in profile.get_posts():
                # Polite delay between each post inspection
                time.sleep(random.uniform(iter_min, iter_max))
                if post.is_video:
                    reel_candidates.append(post)
                if len(reel_candidates) >= max_check:
                    break
        except Exception as exc:
            logger.error(f"Error iterating posts from @{username}: {exc}")

        if not reel_candidates:
            logger.warning(f"No Reels found on @{username}")
            return None

        random.shuffle(reel_candidates)

        for post in reel_candidates:
            post_id = str(post.shortcode)

            # Dedup
            if is_post_reposted(post_id):
                logger.debug(f"Already uploaded {post_id} — skipping")
                continue

            # Content suitability filter
            if not self._is_post_suitable(post):
                continue

            # Polite delay before downloading the selected Reel
            rl = self.config.get("rate_limits", {})
            dl_delay = random.uniform(
                float(rl.get("ig_pre_download_min", 6)),
                float(rl.get("ig_pre_download_max", 15)),
            )
            logger.info(f"Rate-limit: sleeping {dl_delay:.1f}s before Reel download...")
            time.sleep(dl_delay)

            result = self._download_reel(
                post=post,
                username=username,
                download_dir=download_dir,
                add_credit=add_credit,
            )
            if result:
                return result

        logger.info(f"All Reels from @{username} have already been uploaded.")
        return None

    # ── Content filters ───────────────────────────────────────────────────────

    def _is_post_suitable(self, post) -> bool:
        """
        Skip posts that are day-specific (Jummah) or seasonal (Ramadan)
        unless today matches the context.
        """
        from datetime import datetime
        caption = (post.caption or "").lower()
        now     = datetime.now()

        # Friday / Jummah filter
        friday_keywords   = ["friday", "jummah", "jumuah", "جمعة"]
        is_friday_content = any(kw in caption for kw in friday_keywords)
        is_today_friday   = now.weekday() == 4

        if is_friday_content and not is_today_friday:
            logger.info(f"Skipping {post.shortcode}: Jummah content but today is not Friday.")
            return False

        # Ramadan filter
        ramadan_keywords   = ["ramadan", "ramazan", "iftar", "suhoor", "fasting", "رمضان"]
        is_ramadan_content = any(kw in caption for kw in ramadan_keywords)
        is_it_ramadan      = self.config.get("repost", {}).get("is_ramadan", False)

        if is_ramadan_content and not is_it_ramadan:
            logger.info(f"Skipping {post.shortcode}: Ramadan content but is_ramadan=false.")
            return False

        return True

    # ── Download ──────────────────────────────────────────────────────────────

    def _download_reel(
        self,
        post,
        username: str,
        download_dir: str,
        add_credit: bool,
    ) -> Optional[Dict[str, Any]]:
        """Download a Reel .mp4, validate size, mark as uploaded, return result dict."""
        post_id = str(post.shortcode)

        try:
            video_url = post.video_url
            if not video_url:
                logger.warning(f"No video URL found for {post_id}")
                return None

            logger.info(f"Downloading Reel {post_id} from @{username}...")

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }

            resp = requests.get(video_url, headers=headers, timeout=60, stream=True)
            resp.raise_for_status()

            filename   = f"reel_{post_id}.mp4"
            local_path = os.path.abspath(os.path.join(download_dir, filename))

            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)

            file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
            logger.info(f"Downloaded: {filename} ({file_size_mb:.1f} MB)")

            # YouTube Shorts max: ~256 MB / 3 minutes — skip if unreasonably large
            if file_size_mb > 256:
                logger.warning(f"Reel {post_id} is too large ({file_size_mb:.1f} MB) — skipping")
                os.remove(local_path)
                log_repost(post_id)
                return None

            # Mark as uploaded so we never re-download it
            log_repost(post_id)
            logger.info(f"Reel {post_id} ready for YouTube upload.")

            video_dict = {
                "id":             f"reel_{post_id}",
                "local_path":     local_path,
                "is_video":       True,
                "source_post_id": post_id,
                "_cleanup_path":  local_path,
            }

            return {
                "video":            video_dict,
                "original_caption": post.caption or "",
                "source_post_id":   post_id,
            }

        except Exception as exc:
            logger.error(f"Failed to download Reel {post_id}: {exc}", exc_info=True)
            return None
