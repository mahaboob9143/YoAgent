"""
agents/orchestrator.py — Orchestrator for InstaAgent Repost Pipeline.

The Orchestrator coordinates the active agents to pull content from 
target profiles, process it, and push it to Meta Graph API.
"""

from typing import Optional

from agents.poster_agent import PosterAgent
from agents.repost_agent import RepostAgent
from core.logger import get_logger

logger = get_logger("Orchestrator")


class Orchestrator:
    """
    Top-level coordinator for the InstaAgent Repost system.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        
        # Instantiate active agents
        self.poster_agent = PosterAgent()
        self.repost_agent = RepostAgent()

        logger.info(f"Orchestrator ready (dry_run={dry_run})")

    # ── Public API ────────────────────────────────────────────────────────────

    def repost_now(self) -> None:
        """
        Repost mode (--repost).

        Scrapes one unseen image from the configured source account,
        rewrites the caption, and posts to Instagram. Then exits cleanly.
        """
        logger.info("=" * 60)
        logger.info("  REPOST NOW — scrape & publish pipeline (IG + Facebook)")
        logger.info("=" * 60)

        # ── Step 1: Scrape + prepare ───────────────────────────────────────
        logger.info("RepostAgent: fetching post from source account...")
        result = self.repost_agent.run()

        if not result:
            logger.error(
                "RepostAgent returned nothing. "
                "Check repost.enabled=true in config.yaml "
                "and that source_accounts are valid."
            )
            return

        image = result["image"]
        caption = result["caption"]
        source_post_id = result["source_post_id"]

        logger.info(f"Repost ready — source post: {source_post_id}")
        logger.info(f"Caption preview:\n{caption[:300]}...")

        # ── Dry-run shortcut ───────────────────────────────────────────────
        if self.dry_run:
            logger.info("[DRY RUN] Cycle complete — would post:")
            logger.info(f"  Source : {source_post_id}")
            logger.info(f"  Image  : {image.get('local_path', 'N/A')}")
            return

        # ── Step 2: Publish via PosterAgent (Instagram + Facebook) ───────────
        logger.info("Publishing to Instagram (and Facebook if enabled)...")
        ig_post_id: Optional[str] = self.poster_agent.post(
            image=image,
            caption=caption,
            topic="repost",
        )

        if not ig_post_id:
            logger.error("Post failed. Check logs/errors.log for details.")
            return

        logger.info(f"Repost complete. IG post ID: {ig_post_id}")


