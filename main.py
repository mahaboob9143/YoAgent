#!/usr/bin/env python3
"""
YoAgent — Autonomous Islamic YouTube Shorts Pipeline
=====================================================

Scrapes Reels from public Islamic Instagram accounts and uploads them
to YouTube as Shorts, with AI-free auto-generated titles and descriptions.

Usage:
  python main.py --repost           # Scrape one Reel and upload to YouTube Shorts
  python main.py --repost --dry-run # Simulate without uploading

Environment:
  Requires .env file with YouTube OAuth2 credentials and Instagram session.
  Copy .env.template to .env and fill in your credentials.
  Run `python scripts/get_youtube_token.py` once to generate YOUTUBE_REFRESH_TOKEN.

Config:
  All runtime settings live in config.yaml.
"""

import argparse
import os
import sys

import yaml
from dotenv import load_dotenv


# ─── Bootstrap ────────────────────────────────────────────────────────────────

def _load_env_or_exit() -> None:
    """Load .env file. Abort if required variables are missing for the active scrape source."""
    load_dotenv()

    # Determine the active scrape source from config.yaml (default: youtube)
    scrape_source = "youtube"
    if os.path.isfile("config.yaml"):
        try:
            with open("config.yaml", "r", encoding="utf-8") as _f:
                _cfg = yaml.safe_load(_f) or {}
            scrape_source = _cfg.get("scrape_source", "youtube")
        except Exception:
            pass

    # Only require IG credentials when actually scraping Instagram
    if scrape_source == "instagram":
        required = {
            "IG_SESSION_ID": "Instagram session cookie for scraping",
            "IG_SCRAPE_USER": "Instagram username used for session auth",
        }
        missing = {k: v for k, v in required.items() if not os.getenv(k)}
        if missing:
            print("\n❌  Missing required environment variables in .env:\n")
            for var, description in missing.items():
                print(f"     {var:<26} — {description}")
            print("\n  Make sure to fill in your credentials.\n")
            sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yoagent",
        description="Autonomous Islamic YouTube Shorts automation system",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate all steps without actually uploading to YouTube",
    )
    parser.add_argument(
        "--repost",
        action="store_true",
        help=(
            "Scrape one Reel from configured source accounts and "
            "upload it to YouTube as a Short."
        ),
    )
    return parser.parse_args()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Load .env and validate credentials
    _load_env_or_exit()

    # 2. Parse CLI arguments
    args = _parse_args()

    # 3. Check config.yaml is present
    if not os.path.isfile("config.yaml"):
        print(
            "\n❌  config.yaml not found in the current directory.\n"
            "   Make sure you are running from the project root: python main.py\n"
        )
        sys.exit(1)

    # 4. Announce startup mode
    from core.logger import get_logger
    logger = get_logger("Main")

    if not args.repost and not args.dry_run:
        print("\n❌ Please provide the --repost flag to run the pipeline.")
        sys.exit(1)

    mode = "DRY RUN" if args.dry_run else "REPOST → YouTube Shorts"

    logger.info("=" * 60)
    logger.info(f"  YoAgent starting — mode: {mode}")
    logger.info("=" * 60)

    # 5. Instantiate and run the orchestrator
    from agents.orchestrator import Orchestrator
    orchestrator = Orchestrator(dry_run=args.dry_run)
    orchestrator.repost_now()


if __name__ == "__main__":
    main()
