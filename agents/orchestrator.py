"""
agents/orchestrator.py — Orchestrator for YoAgent YouTube Shorts Pipeline.

Coordinates:
  1. RepostAgent  — scrapes a Reel from the configured source account
  2. YouTubeMetadataEngine — builds title, description, tags from the caption
  3. YouTubeUploaderAgent  — uploads the Reel to YouTube as a Short
"""

import os
from typing import Optional

from agents.repost_agent import RepostAgent
from agents.youtube_scraper_agent import YouTubeScraperAgent
from agents.youtube_uploader_agent import YouTubeUploaderAgent
from core.youtube_metadata_engine import build_metadata
from core.logger import get_logger
from core.flags import get_config

logger = get_logger("Orchestrator")


class Orchestrator:
    """Top-level coordinator for the YoAgent YouTube Shorts pipeline."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.config = get_config()
        self.scrape_source = self.config.get("scrape_source", "youtube")
        
        if self.scrape_source == "instagram":
            self.scraper = RepostAgent()
            logger.info("Using Instagram RepostAgent as source")
        else:
            self.scraper = YouTubeScraperAgent()
            logger.info("Using YouTubeScraperAgent as source")
            
        self.uploader = YouTubeUploaderAgent()
        logger.info(f"Orchestrator ready (dry_run={dry_run})")

    # ── Public API ────────────────────────────────────────────────────────────

    def repost_now(self) -> None:
        """
        Full pipeline:
          1. Scrape one unseen Reel/Short from source account
          2. Generate YouTube title / description / tags
          3. Upload to YouTube as a Short (or log intent if dry_run)
          4. Clean up local .mp4 file
        """
        logger.info("=" * 60)
        logger.info("  REPOST NOW — scrape Video → upload to YouTube Shorts")
        logger.info("=" * 60)

        # ── Step 1: Scrape ────────────────────────────────────────────────────
        logger.info("Scraper: fetching video from source...")
        result = self.scraper.run()

        if not result:
            logger.error(
                "Scraper returned nothing. "
                "Check scrape_source in config.yaml "
                "and that source lists are valid."
            )
            return

        video           = result["video"]
        original_caption = result["original_caption"]
        source_post_id  = result["source_post_id"]

        logger.info(f"Video ready — source post: {source_post_id}")

        # ── Step 2: Build YouTube metadata ────────────────────────────────────
        config         = get_config()
        
        if self.scrape_source == "youtube":
            yt_cfg = config.get("youtube_scraper", {})
            credit_handle = video.get("uploader", "YouTube Channel")
            add_credit = yt_cfg.get("add_credit_line", True)
        else:
            repost_cfg = config.get("repost", {})
            credit_handle = (repost_cfg.get("source_accounts") or ["softeningsayings"])[0]
            add_credit = repost_cfg.get("add_credit_line", True)

        metadata = build_metadata(
            original=original_caption,
            add_credit=add_credit,
            credit_handle=credit_handle,
        )

        logger.info(f"Category detected : {metadata['category']}")
        logger.info(f"YouTube title     : {metadata['title']}")

        # ── Step 3: Upload ────────────────────────────────────────────────────
        video_id: Optional[str] = self.uploader.upload(
            video_path=video["local_path"],
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            dry_run=self.dry_run,
        )

        if not video_id:
            logger.error("Upload failed. Check logs for details.")
            self._cleanup(video)
            return

        if not self.dry_run:
            logger.info(f"✅ YouTube Shorts upload complete! Video ID: {video_id}")
            logger.info(f"   https://www.youtube.com/shorts/{video_id}")

        # ── Step 4: Local file cleanup ────────────────────────────────────────
        self._cleanup(video)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cleanup(self, video: dict) -> None:
        """Delete the local .mp4 file after upload (or after dry-run)."""
        cleanup_path = video.get("_cleanup_path") or video.get("local_path")
        if cleanup_path and os.path.exists(cleanup_path):
            try:
                os.remove(cleanup_path)
                logger.info(f"Cleaned up local file: {os.path.basename(cleanup_path)}")
            except Exception as e:
                logger.warning(f"Could not delete local file: {e}")
