"""Dataset and repository statistics."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

from ..extraction.models import MergeRecord

logger = logging.getLogger(__name__)


def compute_stats(records: list[MergeRecord]) -> dict:
    """Compute comprehensive statistics for a list of merge records.

    Args:
        records: List of merge records.

    Returns:
        Dict of statistics.
    """
    if not records:
        return {"total_records": 0}

    type_counts = Counter(r.change_type for r in records if r.change_type)
    difficulty_counts = Counter(r.difficulty for r in records if r.difficulty)
    source_counts = Counter(r.description_source for r in records if r.description_source)
    merge_type_counts = Counter(r.merge_type.value for r in records)
    repo_counts = Counter(r.repo_name for r in records)
    lang_counts: Counter[str] = Counter()
    for r in records:
        lang_counts.update(r.languages)

    total_ins = sum(r.insertions for r in records)
    total_del = sum(r.deletions for r in records)
    total_files = sum(r.num_files for r in records)
    diff_lines = [r.diff_lines for r in records]
    quality_scores = [r.quality_score for r in records if r.quality_score >= 0]

    has_tests = sum(1 for r in records if r.has_test_changes)

    return {
        "total_records": len(records),
        "by_merge_type": dict(merge_type_counts),
        "by_change_type": dict(type_counts),
        "by_difficulty": dict(difficulty_counts),
        "by_description_source": dict(source_counts),
        "by_repo": dict(repo_counts),
        "by_language": dict(lang_counts.most_common(20)),
        "total_insertions": total_ins,
        "total_deletions": total_del,
        "total_files_changed": total_files,
        "avg_files_per_record": round(total_files / len(records), 1),
        "avg_insertions": round(total_ins / len(records), 1),
        "avg_deletions": round(total_del / len(records), 1),
        "diff_lines": {
            "min": min(diff_lines) if diff_lines else 0,
            "max": max(diff_lines) if diff_lines else 0,
            "avg": round(sum(diff_lines) / len(diff_lines), 1) if diff_lines else 0,
            "median": sorted(diff_lines)[len(diff_lines) // 2] if diff_lines else 0,
        },
        "quality_scores": {
            "min": round(min(quality_scores), 3) if quality_scores else 0,
            "max": round(max(quality_scores), 3) if quality_scores else 0,
            "avg": round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else 0,
            "count_scored": len(quality_scores),
        },
        "records_with_tests": has_tests,
        "records_with_tests_pct": round(has_tests / len(records) * 100, 1),
    }


def write_stats(stats: dict, output_path: Path) -> None:
    """Write statistics to a JSON file.

    Args:
        stats: Statistics dict.
        output_path: Path to output JSON file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    logger.info("Wrote stats to %s", output_path)


def format_stats_table(stats: dict) -> str:
    """Format statistics as a human-readable table.

    Args:
        stats: Statistics dict from compute_stats().

    Returns:
        Formatted string.
    """
    lines = [
        f"Total records: {stats.get('total_records', 0)}",
        "",
        "By merge type:",
    ]
    for k, v in stats.get("by_merge_type", {}).items():
        lines.append(f"  {k}: {v}")

    lines.append("\nBy change type:")
    for k, v in stats.get("by_change_type", {}).items():
        lines.append(f"  {k}: {v}")

    lines.append("\nBy difficulty:")
    for k, v in stats.get("by_difficulty", {}).items():
        lines.append(f"  {k}: {v}")

    lines.append("\nBy description source:")
    for k, v in stats.get("by_description_source", {}).items():
        lines.append(f"  {k}: {v}")

    if len(stats.get("by_repo", {})) > 1:
        lines.append("\nBy repository:")
        for k, v in stats.get("by_repo", {}).items():
            lines.append(f"  {k}: {v}")

    lines.append(f"\nLanguages: {', '.join(k for k, _ in stats.get('by_language', {}).items())}")

    diff_stats = stats.get("diff_lines", {})
    lines.append(
        f"\nDiff lines: min={diff_stats.get('min', 0)}, avg={diff_stats.get('avg', 0)}, max={diff_stats.get('max', 0)}"
    )

    test_count = stats.get("records_with_tests", 0)
    test_pct = stats.get("records_with_tests_pct", 0)
    lines.append(f"Records with tests: {test_count} ({test_pct}%)")
    lines.append(
        f"Total changes: +{stats.get('total_insertions', 0)}/-{stats.get('total_deletions', 0)} "
        f"across {stats.get('total_files_changed', 0)} files"
    )

    return "\n".join(lines)
