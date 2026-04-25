"""
core/post_state.py — Tracks the last post type to enforce alternating pattern.

Stores 'image' or 'reel' in data/last_post_type.txt.
On each run, the bot checks this file to decide which type to post next.

Pattern: image → reel → image → reel → ...
"""

from pathlib import Path

_STATE_FILE = Path("data/last_post_type.txt")


def _ensure_file() -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _STATE_FILE.exists():
        # Default: pretend last was a reel so we start with an image
        _STATE_FILE.write_text("reel", encoding="utf-8")


def get_last_post_type() -> str:
    """Return 'image' or 'reel' — whichever was posted last."""
    _ensure_file()
    return _STATE_FILE.read_text(encoding="utf-8").strip().lower()


def get_next_post_type() -> str:
    """Return which type should be posted next based on the alternating pattern."""
    last = get_last_post_type()
    return "reel" if last == "image" else "image"


def save_post_type(post_type: str) -> None:
    """Save the type of the post that was just published ('image' or 'reel')."""
    _ensure_file()
    _STATE_FILE.write_text(post_type.strip().lower(), encoding="utf-8")
