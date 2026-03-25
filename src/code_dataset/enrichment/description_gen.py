"""Generate synthetic task descriptions from code diffs.

Uses DSPy ChainOfThought(MergeDescription) to reverse-engineer what task
or issue would have produced the given code changes. This is the core
innovation: turning unlabeled code diffs into instruction-tuning data.
"""

from __future__ import annotations

import logging

import dspy

from ..extraction.models import MergeRecord
from .signatures import MergeDescription

logger = logging.getLogger(__name__)

# Maximum diff size to send to LLM (characters). Larger diffs are truncated.
_MAX_DIFF_CHARS = 30000


def _truncate_diff(diff: str, max_chars: int = _MAX_DIFF_CHARS) -> str:
    """Truncate a diff to fit within LLM context limits."""
    if len(diff) <= max_chars:
        return diff
    # Keep the first portion and add a truncation notice
    truncated = diff[:max_chars]
    # Try to cut at a line boundary
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars * 0.8:
        truncated = truncated[:last_newline]
    remaining = len(diff) - len(truncated)
    truncated += f"\n\n... [truncated {remaining} characters]"
    return truncated


def generate_description(record: MergeRecord) -> MergeRecord:
    """Generate a synthetic task description for a merge record.

    Uses ChainOfThought for better reasoning about the code changes.

    Args:
        record: A merge record with a diff but poor/missing description.

    Returns:
        The same record with title, description, change_type, difficulty,
        and languages fields filled in.
    """
    generator = dspy.ChainOfThought(MergeDescription)

    diff = _truncate_diff(record.diff)
    file_list = "\n".join(f.path for f in record.files_changed)
    commit_messages = record.combined_commit_messages

    result = generator(
        diff=diff,
        branch_name=record.branch_name,
        commit_messages=commit_messages,
        file_list=file_list,
    )

    record.title = str(result.title).strip()
    record.description = str(result.description).strip()
    record.change_type = _normalize_change_type(str(result.change_type))
    record.difficulty = _normalize_difficulty(str(result.difficulty))
    record.languages = _normalize_languages(result.languages)
    record.description_source = "synthetic"

    return record


def _normalize_change_type(value: str) -> str:
    """Normalize change type to one of the valid values."""
    normalized = value.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    # Handle common variations
    mapping = {
        "bug": "bugfix",
        "bugfix": "bugfix",
        "fix": "bugfix",
        "feat": "feature",
        "feature": "feature",
        "refactor": "refactor",
        "refactoring": "refactor",
        "test": "test",
        "tests": "test",
        "testing": "test",
        "doc": "docs",
        "docs": "docs",
        "documentation": "docs",
        "chore": "chore",
        "maintenance": "chore",
        "ci": "chore",
        "build": "chore",
    }
    return mapping.get(normalized, "feature")


def _normalize_difficulty(value: str) -> str:
    """Normalize difficulty to easy/medium/hard."""
    normalized = value.strip().lower()
    if "easy" in normalized or "simple" in normalized or "trivial" in normalized:
        return "easy"
    if "hard" in normalized or "complex" in normalized or "difficult" in normalized:
        return "hard"
    return "medium"


def _normalize_languages(languages) -> list[str]:
    """Normalize language list."""
    if isinstance(languages, str):
        languages = [lang.strip() for lang in languages.split(",")]
    return [lang.strip().lower() for lang in languages if lang.strip()]


def enrich_records(
    records: list[MergeRecord],
    max_calls: int = 500,
    skip_if_enriched: bool = True,
) -> list[MergeRecord]:
    """Generate synthetic descriptions for a batch of records.

    Args:
        records: List of merge records needing descriptions.
        max_calls: Maximum number of LLM calls to make.
        skip_if_enriched: Skip records that already have descriptions.

    Returns:
        The records with descriptions filled in.
    """
    enriched = 0
    errors = 0

    for record in records:
        if enriched >= max_calls:
            logger.warning("Reached max LLM calls (%d), stopping enrichment", max_calls)
            break

        if skip_if_enriched and record.description_source:
            continue

        try:
            generate_description(record)
            enriched += 1
            logger.debug("Enriched %s: %s", record.id, record.title)
        except Exception as e:
            errors += 1
            logger.warning("Failed to enrich %s: %s", record.id, e)

    logger.info(
        "Enrichment complete: %d generated, %d errors, %d skipped",
        enriched,
        errors,
        len(records) - enriched - errors,
    )
    return records
