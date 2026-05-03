"""
agents/youtube_uploader_agent.py — YouTubeUploaderAgent for YoAgent.

Responsibilities:
  1. Build an authenticated YouTube Data API v3 service using a stored OAuth2 refresh token.
  2. Upload a local .mp4 file using the resumable upload protocol (chunk-safe for large videos).
  3. Set the video's title, description, tags, category, and privacy status.
  4. Return the YouTube video ID on success, or None on failure.

Authentication flow (headless / GitHub Actions):
  - Credentials are stored as env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
  - Run `python scripts/get_youtube_token.py` locally once to generate the refresh token.
"""

import os
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from core.flags import get_config
from core.logger import get_logger
from core.retry import retry

logger = get_logger("YouTubeUploader")

_YT_API_SERVICE = "youtube"
_YT_API_VERSION = "v3"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploaderAgent:
    """Uploads Reels to YouTube as Shorts using the Data API v3."""

    def __init__(self):
        self.client_id     = os.getenv("YOUTUBE_CLIENT_ID")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        self.config        = get_config()

    def is_configured(self) -> bool:
        """Returns True only if all three YouTube OAuth2 env vars are set."""
        return bool(self.client_id and self.client_secret and self.refresh_token)

    # ── Public entry point ────────────────────────────────────────────────────

    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        dry_run: bool = False,
    ) -> Optional[str]:
        """
        Upload a local video file to YouTube.

        Args:
            video_path:   Absolute path to the .mp4 file.
            title:        YouTube video title (max 100 chars).
            description:  Full video description with hashtags.
            tags:         List of tag strings for discoverability.
            dry_run:      If True, log intent without calling the API.

        Returns:
            YouTube video ID string on success, None on failure.
        """
        # ── Dry-run shortcut ──────────────────────────────────────────────────
        if dry_run:
            logger.info("[DRY RUN] Would upload to YouTube Shorts:")
            logger.info(f"  File   : {os.path.basename(video_path)}")
            logger.info(f"  Title  : {title}")
            logger.info(f"  Tags   : {tags[:6]}")
            logger.info(f"  Desc   :\n{description[:300]}...")
            return "DRY_RUN_VIDEO_ID"

        # ── Credential check ──────────────────────────────────────────────────
        if not self.is_configured():
            logger.error(
                "YouTube credentials missing. "
                "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, "
                "YOUTUBE_REFRESH_TOKEN in .env (or GitHub Secrets). "
                "Run `python scripts/get_youtube_token.py` to generate them."
            )
            return None

        if not os.path.isfile(video_path):
            logger.error(f"Video file not found: {video_path}")
            return None

        # ── Config ────────────────────────────────────────────────────────────
        yt_cfg        = self.config.get("youtube", {})
        privacy       = yt_cfg.get("privacy_status", "public")
        category_id   = str(yt_cfg.get("category_id", "22"))   # 22 = People & Blogs
        made_for_kids = yt_cfg.get("made_for_kids", False)

        try:
            logger.info("Authenticating with YouTube Data API v3...")
            service = self._build_service()

            body = {
                "snippet": {
                    "title":       title[:100],
                    "description": description,
                    "tags":        tags,
                    "categoryId":  category_id,
                },
                "status": {
                    "privacyStatus":           privacy,
                    "selfDeclaredMadeForKids": made_for_kids,
                },
            }

            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info(
                f"Starting resumable upload: {os.path.basename(video_path)} "
                f"({file_size_mb:.1f} MB) → YouTube Shorts [{privacy}]..."
            )

            media = MediaFileUpload(
                video_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=10 * 1024 * 1024,   # 10 MB chunks
            )

            insert_request = service.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media,
            )

            video_id = self._execute_resumable_upload(insert_request)
            if video_id:
                logger.info(f"✅ Uploaded to YouTube Shorts! Video ID: {video_id}")
                logger.info(f"   https://www.youtube.com/shorts/{video_id}")
            return video_id

        except Exception as exc:
            logger.error(f"YouTube upload failed: {exc}", exc_info=True)
            return None

    # ── Internal helpers ──────────────────────────────────────────────────────

    @retry(max_attempts=3, backoff_factor=2, initial_wait=5.0, exceptions=(Exception,))
    def _build_service(self):
        """Build an authenticated YouTube API service using the refresh token.
        Retried up to 3x with exponential backoff in case of transient token errors.
        """
        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=_SCOPES,
        )
        creds.refresh(Request())   # Exchange refresh_token → access_token
        return build(_YT_API_SERVICE, _YT_API_VERSION, credentials=creds)

    @retry(max_attempts=3, backoff_factor=3, initial_wait=15.0, exceptions=(Exception,))
    def _execute_resumable_upload(self, request) -> Optional[str]:
        """
        Drive a resumable upload to completion, logging progress every chunk.
        Retried up to 3x (15s → 45s → give up) for transient network drops.
        Returns the YouTube video ID from the final response.
        """
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info(f"Upload progress: {pct}%")

        return response.get("id")
