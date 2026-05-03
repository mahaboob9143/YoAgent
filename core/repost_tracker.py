"""
core/repost_tracker.py — Lightweight dedup tracker using a plain text file.

Stores one post ID per line in data/reposted_ids.txt.
Cloud-friendly, zero-dependency tracking — committed to Git by CI after each run.

Performance: IDs are cached in a module-level set on first load, giving O(1)
lookup regardless of how many IDs accumulate over time.

Usage:
    from core.repost_tracker import is_reposted, mark_reposted

    if not is_reposted("DU3i6qPDTOH"):
        # process and post...
        mark_reposted("DU3i6qPDTOH")
"""

from pathlib import Path
from typing import Optional

_TRACKER_FILE = Path("data/reposted_ids.txt")

# In-memory cache — loaded once per process, kept in sync on writes.
_id_cache: Optional[set] = None


def _ensure_file() -> None:
    _TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _TRACKER_FILE.exists():
        _TRACKER_FILE.touch()


def _get_cache() -> set:
    """Return the in-memory ID set, loading from disk on first call."""
    global _id_cache
    if _id_cache is None:
        _ensure_file()
        raw = _TRACKER_FILE.read_text(encoding="utf-8").splitlines()
        _id_cache = {line.strip() for line in raw if line.strip()}
    return _id_cache


def is_reposted(post_id: str) -> bool:
    """Return True if this ID has already been uploaded (O(1) set lookup)."""
    return post_id.strip() in _get_cache()


def mark_reposted(post_id: str) -> None:
    """Append an ID to the tracker file and update the in-memory cache."""
    clean_id = post_id.strip()
    _get_cache().add(clean_id)          # keep cache in sync
    _ensure_file()
    with open(_TRACKER_FILE, "a", encoding="utf-8") as f:
        f.write(clean_id + "\n")


def all_reposted() -> list:
    """Return all tracked post IDs (for debugging/inspection)."""
    return sorted(_get_cache())
