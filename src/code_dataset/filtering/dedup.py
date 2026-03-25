"""Near-duplicate detection for merge records.

Uses a simple but effective approach: hash the sorted list of changed file paths
plus a normalized diff fingerprint. Records with identical fingerprints are
considered duplicates (e.g., cherry-picks, back-merges).
"""

from __future__ import annotations

import hashlib
import logging
import re

from ..extraction.models import MergeRecord

logger = logging.getLogger(__name__)

# Strip line numbers and whitespace from diffs for normalization
_HUNK_HEADER_RE = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@.*$", re.MULTILINE)
_EMPTY_LINES_RE = re.compile(r"\n{3,}")


def _fingerprint(record: MergeRecord) -> str:
    """Compute a content fingerprint for a merge record.

    The fingerprint is based on:
    - Sorted list of changed file paths
    - Normalized diff content (without line numbers)

    This catches cherry-picks and identical changes across branches.
    """
    # File paths
    paths = sorted(f.path for f in record.files_changed)
    path_str = "\n".join(paths)

    # Normalize diff: remove hunk headers (line numbers change) and collapse whitespace
    normalized_diff = _HUNK_HEADER_RE.sub("", record.diff)
    normalized_diff = _EMPTY_LINES_RE.sub("\n\n", normalized_diff)
    normalized_diff = normalized_diff.strip()

    combined = f"{path_str}\n---\n{normalized_diff}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def deduplicate(records: list[MergeRecord]) -> list[MergeRecord]:
    """Remove near-duplicate merge records.

    Keeps the first occurrence (by order in the list). Records with
    identical content fingerprints are removed.

    Args:
        records: List of merge records.

    Returns:
        Deduplicated list (preserving original order).
    """
    seen: set[str] = set()
    unique: list[MergeRecord] = []
    duplicates = 0

    for record in records:
        fp = _fingerprint(record)
        if fp in seen:
            duplicates += 1
            logger.debug("Duplicate detected: %s (fingerprint %s)", record.id, fp)
            continue
        seen.add(fp)
        unique.append(record)

    if duplicates > 0:
        logger.info(
            "Removed %d duplicates, kept %d unique records",
            duplicates,
            len(unique),
        )

    return unique
