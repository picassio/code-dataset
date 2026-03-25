"""SFT (Supervised Fine-Tuning) dataset formatter.

Produces instruction → patch pairs suitable for fine-tuning code LLMs.
Each record maps a task description to the code changes that implement it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..extraction.models import MergeRecord
from .context_window import build_context, build_response_files

logger = logging.getLogger(__name__)


def format_sft_record(record: MergeRecord, max_context_tokens: int = 8192) -> dict:
    """Format a single merge record as an SFT training example.

    Args:
        record: Enriched merge record with description.
        max_context_tokens: Token budget for file context.

    Returns:
        Dict in SFT format.
    """
    title = record.title or record.merge_message.strip().split("\n")[0]
    description = record.description or ""

    if title and description and description != title:
        instruction = f"{title}\n\n{description}"
    elif description:
        instruction = description
    else:
        instruction = title

    context_files = build_context(record, max_context_tokens)
    response_files = build_response_files(record)

    return {
        "id": record.id,
        "instruction": instruction,
        "context": {
            "files_before": context_files,
            "repo_structure": record.repo_tree,
        },
        "response": {
            "diff": record.diff,
            "files_after": response_files,
        },
        "metadata": {
            "repo_name": record.repo_name,
            "merge_sha": record.merge_sha,
            "merge_type": record.merge_type.value,
            "branch": record.branch_name,
            "num_commits": len(record.branch_commits),
            "files_changed": record.num_files,
            "insertions": record.insertions,
            "deletions": record.deletions,
            "description_source": record.description_source,
            "change_type": record.change_type,
            "difficulty": record.difficulty,
            "languages": record.languages,
            "has_tests": record.has_test_changes,
            "quality_score": record.quality_score,
        },
    }


def write_sft_dataset(
    records: list[MergeRecord],
    output_path: Path,
    max_context_tokens: int = 8192,
) -> int:
    """Write an SFT dataset to a JSONL file.

    Args:
        records: Enriched merge records.
        output_path: Path to output JSONL file.
        max_context_tokens: Token budget for context.

    Returns:
        Number of records written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            if not record.title and not record.description:
                logger.debug("Skipping %s: no description", record.id)
                continue

            entry = format_sft_record(record, max_context_tokens)
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")
            count += 1

    logger.info("Wrote %d SFT records to %s", count, output_path)
    return count
