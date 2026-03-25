"""Score the quality of existing merge descriptions.

Uses DSPy DescriptionQuality signature to determine if a commit message
is good enough to use as training data, or needs synthetic regeneration.
"""

from __future__ import annotations

import logging

import dspy

from ..extraction.models import MergeRecord
from .signatures import DescriptionQuality

logger = logging.getLogger(__name__)


def _build_diff_summary(record: MergeRecord) -> str:
    """Build a brief summary of the diff for quality scoring."""
    file_names = ", ".join(f.path for f in record.files_changed[:10])
    if len(record.files_changed) > 10:
        file_names += f" ... and {len(record.files_changed) - 10} more"
    return f"{record.num_files} files changed, +{record.insertions}/-{record.deletions} lines. Files: {file_names}"


def score_description(record: MergeRecord) -> tuple[float, bool, str]:
    """Score the quality of a merge record's description.

    Args:
        record: The merge record with a merge_message to evaluate.

    Returns:
        Tuple of (quality_score, is_instructive, reason).
    """
    scorer = dspy.Predict(DescriptionQuality)

    description = record.merge_message
    if record.branch_commits:
        # Include branch commit messages for context
        all_messages = [description] + [c.message for c in record.branch_commits if c.message != description]
        description = "\n---\n".join(msg for msg in all_messages if msg.strip())

    result = scorer(
        description=description,
        diff_summary=_build_diff_summary(record),
    )

    score = float(result.quality_score)
    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))

    return score, bool(result.is_instructive), str(result.reason)


def score_records(
    records: list[MergeRecord],
    threshold: float = 0.5,
) -> tuple[list[MergeRecord], list[MergeRecord]]:
    """Score all records and split into good/needs-enrichment.

    Args:
        records: List of merge records.
        threshold: Quality threshold (below this → needs enrichment).

    Returns:
        Tuple of (good_records, needs_enrichment_records).
    """
    good: list[MergeRecord] = []
    needs_enrichment: list[MergeRecord] = []

    for record in records:
        try:
            score, is_instructive, reason = score_description(record)
            record.quality_score = score

            if score >= threshold and is_instructive:
                record.description_source = "original"
                record.description = record.merge_message
                good.append(record)
                logger.debug("Good description (%.2f): %s — %s", score, record.id, reason)
            else:
                needs_enrichment.append(record)
                logger.debug("Needs enrichment (%.2f): %s — %s", score, record.id, reason)
        except Exception as e:
            logger.warning("Failed to score %s: %s", record.id, e)
            needs_enrichment.append(record)

    logger.info(
        "Description quality: %d good (>=%.1f), %d need enrichment",
        len(good),
        threshold,
        len(needs_enrichment),
    )
    return good, needs_enrichment
