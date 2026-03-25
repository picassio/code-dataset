"""Classify merge records by change type and difficulty.

Uses DSPy DiffClassifier signature for lightweight classification
without full description generation.
"""

from __future__ import annotations

import logging

import dspy

from ..extraction.models import MergeRecord
from .description_gen import _normalize_change_type, _normalize_difficulty, _truncate_diff
from .signatures import DiffClassifier

logger = logging.getLogger(__name__)


def classify_record(record: MergeRecord) -> MergeRecord:
    """Classify a single merge record by type and difficulty.

    Args:
        record: The merge record to classify.

    Returns:
        The same record with change_type and difficulty filled in.
    """
    classifier = dspy.Predict(DiffClassifier)

    diff = _truncate_diff(record.diff)
    file_list = "\n".join(f.path for f in record.files_changed)

    result = classifier(diff=diff, file_list=file_list)

    record.change_type = _normalize_change_type(str(result.change_type))
    record.difficulty = _normalize_difficulty(str(result.difficulty))

    if not record.title:
        record.title = str(result.summary).strip()

    return record


def classify_records(records: list[MergeRecord], max_calls: int = 500) -> list[MergeRecord]:
    """Classify a batch of records.

    Only classifies records that don't already have a change_type.

    Args:
        records: List of merge records.
        max_calls: Maximum LLM calls.

    Returns:
        Records with classification filled in.
    """
    classified = 0
    errors = 0

    for record in records:
        if classified >= max_calls:
            logger.warning("Reached max LLM calls (%d), stopping classification", max_calls)
            break

        if record.change_type and record.difficulty:
            continue

        try:
            classify_record(record)
            classified += 1
        except Exception as e:
            errors += 1
            logger.warning("Failed to classify %s: %s", record.id, e)

    logger.info("Classified %d records (%d errors)", classified, errors)
    return records
