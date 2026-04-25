"""
agents/facebook_poster_agent.py — Posts content to a Facebook Page via Meta Graph API.

Follows the same pattern as PosterAgent (Instagram), posting:
  - Images: POST /{page_id}/photos
  - Videos/Reels: POST /{page_id}/videos

Facebook Graph API is simpler than Instagram — no container/polling flow.
Images and videos are published in a single API call.
"""

import os
import time
import random
from typing import Optional

import requests

from core.logger import get_logger
from core.retry import retry
from core.flags import get_config

logger = get_logger("FacebookPoster")

_GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class FacebookPosterAgent:
    """
    Publishes images and videos to a Facebook Page via the Meta Graph API.
    Works in parallel with PosterAgent — same content, second platform.
    """

    def __init__(self):
        self.access_token: Optional[str] = os.getenv("FB_PAGE_ACCESS_TOKEN")
        self.page_id: Optional[str] = os.getenv("FB_PAGE_ID")

    def is_configured(self) -> bool:
        """Returns True only if both FB credentials are present."""
        return bool(self.access_token and self.page_id)

    # ── Public entry point ────────────────────────────────────────────────────

    def post(self, image: dict, caption: str, is_reel: bool = False) -> Optional[str]:
        """
        Publish media to the Facebook Page.

        Args:
            image:    Image/video dict from RepostAgent (same format as PosterAgent).
            caption:  Caption string.
            is_reel:  True if the media is a video.

        Returns:
            Facebook post ID on success, None on failure.
        """
        if not self.is_configured():
            logger.warning("FB_PAGE_ACCESS_TOKEN or FB_PAGE_ID not set — skipping Facebook post.")
            return None

        # Facebook uses the Cloudinary URL directly — no separate container needed
        # The URL is passed from the orchestrator after Cloudinary upload
        media_url: str = image.get("cloudinary_url", "")
        if not media_url:
            logger.error("No Cloudinary URL found in image dict for Facebook post.")
            return None

        if is_reel:
            return self._post_video(video_url=media_url, caption=caption)
        else:
            return self._post_photo(image_url=media_url, caption=caption)

    # ── Photo publishing ──────────────────────────────────────────────────────

    @retry(
        max_attempts=3,
        backoff_factor=2,
        initial_wait=5.0,
        exceptions=(requests.RequestException,),
    )
    def _post_photo(self, image_url: str, caption: str) -> Optional[str]:
        """POST /{page_id}/photos — publish a photo to the Page feed."""
        url = f"{_GRAPH_API_BASE}/{self.page_id}/photos"
        data = {
            "url": image_url,
            "caption": caption,
            "access_token": self.access_token,
        }

        logger.info("Facebook API: publishing photo to Page feed...")
        resp = requests.post(url, data=data, timeout=30)

        if not resp.ok:
            self._log_error(resp)
            return None

        post_id = resp.json().get("post_id") or resp.json().get("id")
        logger.info(f"✅ Facebook photo posted! Post ID: {post_id}")
        return post_id

    # ── Video publishing ──────────────────────────────────────────────────────

    @retry(
        max_attempts=3,
        backoff_factor=2,
        initial_wait=5.0,
        exceptions=(requests.RequestException,),
    )
    def _post_video(self, video_url: str, caption: str) -> Optional[str]:
        """POST /{page_id}/videos — publish a video/reel to the Page."""
        url = f"{_GRAPH_API_BASE}/{self.page_id}/videos"
        data = {
            "file_url": video_url,
            "description": caption,
            "access_token": self.access_token,
        }

        logger.info("Facebook API: publishing video to Page feed...")
        resp = requests.post(url, data=data, timeout=60)

        if not resp.ok:
            self._log_error(resp)
            return None

        post_id = resp.json().get("id")
        logger.info(f"✅ Facebook video posted! Post ID: {post_id}")
        return post_id

    # ── Error handler ─────────────────────────────────────────────────────────

    def _log_error(self, resp: requests.Response) -> None:
        """Log a structured Meta API error."""
        try:
            err = resp.json().get("error", {})
            code = err.get("code")
            msg = err.get("message", "")
            logger.error(
                f"Facebook API error — HTTP {resp.status_code} | "
                f"code={code} | {msg}"
            )
            if code == 190:
                logger.critical("→ FB token expired. Regenerate at developers.facebook.com")
            elif code == 200:
                logger.error("→ Missing page permission. Check pages_manage_posts scope.")
        except Exception:
            logger.error(f"Facebook API HTTP {resp.status_code}: {resp.text[:500]}")
