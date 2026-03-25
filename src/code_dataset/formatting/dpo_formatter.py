"""DPO (Direct Preference Optimization) dataset formatter.

Produces chosen/rejected pairs from merge records. Sources of preference:

1. **Revision within a branch**: For merge commits with multiple branch
   commits, the early partial diff (first half of commits) serves as
   "rejected" and the full final diff as "chosen". This represents the
   natural iteration: incomplete → complete code.

Note: DPO pairs require merge commits with >= 3 branch commits to have
meaningful revision history. Squash merges (single commit) cannot produce
DPO pairs because there's no intermediate state available.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..extraction.models import MergeRecord

logger = logging.getLogger(__name__)


def _extract_revision_pair(record: MergeRecord) -> dict | None:
    """Create a preference pair from branch revision history.

    Uses the natural code review iteration as signal:
    - "rejected" = partial diff from the first half of branch commits
      (typically incomplete, pre-review code)
    - "chosen" = full final diff (complete, reviewed, merged code)

    Only works for merge commits with >= 3 branch commits.
    """
    if len(record.branch_commits) < 3:
        return None

    midpoint = len(record.branch_commits) // 2
    early_commits = record.branch_commits[:midpoint]
    final_commits = record.branch_commits[midpoint:]

    instruction = record.title
    if record.description and record.description != record.title:
        instruction = f"{record.title}\n\n{record.description}"

    return {
        "id": f"{record.id}/revision",
        "prompt": instruction,
        "chosen": record.diff,
        "rejected": {
            "commit_messages": [c.message for c in early_commits],
            "num_commits": len(early_commits),
            "note": "Partial implementation from early branch commits (pre-review)",
        },
        "metadata": {
            "repo_name": record.repo_name,
            "merge_sha": record.merge_sha,
            "pair_source": "revision_history",
            "total_commits": len(record.branch_commits),
            "early_commits": len(early_commits),
            "final_commits": len(final_commits),
            "change_type": record.change_type,
            "difficulty": record.difficulty,
            "languages": record.languages,
        },
    }


def format_dpo_records(records: list[MergeRecord]) -> list[dict]:
    """Generate DPO preference pairs from merge records.

    Only merge commits with >= 3 branch commits produce pairs. Squash
    merges are skipped because they have no intermediate states.

    Args:
        records: Enriched merge records.

    Returns:
        List of DPO pair dicts.
    """
    pairs: list[dict] = []

    for record in records:
        if not record.title:
            continue

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
