"""DPO (Direct Preference Optimization) dataset formatter.

Produces chosen/rejected pairs from merge records. Sources of preference:
1. Revision within a branch: early incomplete commit vs final merged state
2. Revert detection: reverted code (rejected) vs replacement (chosen)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..extraction.models import MergeRecord

logger = logging.getLogger(__name__)


def _extract_revision_pair(record: MergeRecord) -> dict | None:
    """Try to create a preference pair from branch revision history.

    If the branch has multiple commits, the first commit's state is "rejected"
    (incomplete) and the final state is "chosen" (complete, reviewed).

    Only works for merge commits with >= 3 branch commits (meaningful iteration).
    """
    if len(record.branch_commits) < 3:
        return None

    # The early commits likely represent incomplete work
    early_messages = [c.message for c in record.branch_commits[: len(record.branch_commits) // 2]]
    final_messages = [c.message for c in record.branch_commits[len(record.branch_commits) // 2 :]]

    instruction = record.title
    if record.description:
        instruction = f"{record.title}\n\n{record.description}"

    return {
        "id": f"{record.id}/revision",
        "prompt": instruction,
        "chosen": record.diff,
        "rejected_context": {
            "early_commit_messages": early_messages,
            "note": "Early branch state — incomplete implementation before review iterations",
        },
        "chosen_context": {
            "final_commit_messages": final_messages,
            "note": "Final merged state — complete, reviewed implementation",
        },
        "metadata": {
            "repo_name": record.repo_name,
            "merge_sha": record.merge_sha,
            "pair_source": "revision_history",
            "num_commits": len(record.branch_commits),
            "change_type": record.change_type,
            "difficulty": record.difficulty,
        },
    }


def format_dpo_records(records: list[MergeRecord]) -> list[dict]:
    """Generate DPO preference pairs from merge records.

    Args:
        records: Enriched merge records.

    Returns:
        List of DPO pair dicts.
    """
    pairs: list[dict] = []

    for record in records:
        if not record.title:
            continue

        # Try revision-based pairs
        pair = _extract_revision_pair(record)
        if pair:
            pairs.append(pair)

    return pairs


def write_dpo_dataset(records: list[MergeRecord], output_path: Path) -> int:
    """Write a DPO dataset to a JSONL file.

    Args:
        records: Enriched merge records.
        output_path: Path to output JSONL file.

    Returns:
        Number of pairs written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pairs = format_dpo_records(records)

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False))
            f.write("\n")

    logger.info("Wrote %d DPO pairs to %s", len(pairs), output_path)
    return len(pairs)
