#!/usr/bin/env python3
"""
InstaAgent — Autonomous Islamic Instagram Content System
========================================================

A cloud-native multi-agent system for maximizing Instagram engagement 
for an Islamic cinematic content account via Reposting.

Usage:
  python main.py --repost           # Scrape @softeningsayings and repost one image

Environment:
  Requires .env file with META_ACCESS_TOKEN and IG_ACCOUNT_ID.
  Copy .env.template to .env and fill in your credentials.

Config:
  All runtime settings and feature flags live in config.yaml.
"""

import argparse
import os
import sys

from dotenv import load_dotenv


# ─── Bootstrap ────────────────────────────────────────────────────────────────

def _load_env_or_exit() -> None:
    """Load .env file. Abort if required variables are missing."""
    load_dotenv()

    required = {
        "META_ACCESS_TOKEN": "Long-lived Meta access token",
        "IG_ACCOUNT_ID":     "Instagram Business/Creator account ID",
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
        prog="instaagent",
        description="Autonomous Islamic Instagram automation system",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate all steps without actually posting to Instagram",
    )
    parser.add_argument(
        "--repost",
        action="store_true",
        help=(
            "Scrape one image from configured source accounts, rewrite its caption, "
            "and publish to your Instagram."
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

    mode = "DRY RUN" if args.dry_run else "REPOST (scrape + publish)"
    
    if not args.repost and not args.dry_run:
        print("\n❌ Please provide the --repost flag to run the pipeline.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"  InstaAgent starting — mode: {mode}")
    logger.info("=" * 60)

    # 5. Instantiate and run the orchestrator
    from agents.orchestrator import Orchestrator
    orchestrator = Orchestrator(dry_run=args.dry_run)

    orchestrator.repost_now()


if __name__ == "__main__":
    main()
