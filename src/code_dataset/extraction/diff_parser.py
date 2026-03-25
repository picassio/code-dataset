"""Parse git diffs and extract file-level change information."""

from __future__ import annotations

import logging
import re

from git import Commit, Diff, Repo

from .models import FileChange

logger = logging.getLogger(__name__)

# Matches @@ -start,count +start,count @@ lines
_HUNK_HEADER = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@")


def get_diff_text(repo: Repo, commit_a: Commit, commit_b: Commit) -> str:
    """Get the unified diff between two commits.

    Args:
        repo: GitPython Repo instance.
        commit_a: The base commit (before).
        commit_b: The target commit (after).

    Returns:
        Unified diff as a string.
    """
    try:
        return repo.git.diff(commit_a.hexsha, commit_b.hexsha, unified=3)
    except Exception as e:
        logger.warning(
            "Failed to get diff between %s..%s: %s",
            commit_a.hexsha[:8],
            commit_b.hexsha[:8],
            e,
        )
        return ""


def get_file_changes(
    repo: Repo,
    commit_a: Commit,
    commit_b: Commit,
    include_content: bool = True,
    max_file_size_kb: int = 100,
) -> list[FileChange]:
    """Extract per-file change information between two commits.

    Args:
        repo: GitPython Repo instance.
        commit_a: The base commit.
        commit_b: The target commit.
        include_content: Whether to include full file contents before/after.
        max_file_size_kb: Skip file contents larger than this (in KB).

    Returns:
        List of FileChange objects.
    """
    try:
        diffs: list[Diff] = commit_a.diff(commit_b)
    except Exception as e:
        logger.warning("Failed to compute diff: %s", e)
        return []

    changes: list[FileChange] = []
    for d in diffs:
        path = d.b_path or d.a_path or ""
        old_path = d.a_path if d.a_path != d.b_path else None

        fc = FileChange(
            path=path,
            old_path=old_path,
            is_binary=_is_binary_diff(d),
            is_new=d.new_file,
            is_deleted=d.deleted_file,
        )

        if not fc.is_binary and include_content:
            fc.content_before = _safe_blob_content(d.a_blob, max_file_size_kb)
            fc.content_after = _safe_blob_content(d.b_blob, max_file_size_kb)

        changes.append(fc)

    # Calculate per-file insertions/deletions from diff stat
    _fill_stats(repo, commit_a, commit_b, changes)

    return changes


def _is_binary_diff(d: Diff) -> bool:
    """Check if a diff represents a binary file change."""
    # GitPython's diff.a_blob/b_blob can tell us
    try:
        if d.a_blob and d.a_blob.mime_type and not d.a_blob.mime_type.startswith("text"):
            return True
        if d.b_blob and d.b_blob.mime_type and not d.b_blob.mime_type.startswith("text"):
            return True
    except Exception:
        pass
    return False


def _safe_blob_content(blob, max_size_kb: int) -> str | None:
    """Safely read blob content, respecting size limits."""
    if blob is None:
        return None
    try:
        if blob.size > max_size_kb * 1024:
            return None
        data = blob.data_stream.read()
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_numstat_path(raw_path: str) -> list[str]:
    """Parse a numstat path, handling rename syntax.

    Git numstat outputs renames as: dir/{old.py => new.py}
    or: old_path => new_path

    Returns:
        List of possible path strings (both old and new for renames).
    """
    # Handle {old => new} syntax: "dir/{old.py => new.py}"
    rename_match = re.match(r"(.*)?\{(.+?) => (.+?)\}(.*)?", raw_path)
    if rename_match:
        prefix = rename_match.group(1) or ""
        old_name = rename_match.group(2)
        new_name = rename_match.group(3)
        suffix = rename_match.group(4) or ""
        return [f"{prefix}{old_name}{suffix}", f"{prefix}{new_name}{suffix}"]

    # Handle "old => new" syntax
    if " => " in raw_path:
        old_path, new_path = raw_path.split(" => ", 1)
        return [old_path.strip(), new_path.strip()]

    return [raw_path]


def _fill_stats(
    repo: Repo,
    commit_a: Commit,
    commit_b: Commit,
    changes: list[FileChange],
) -> None:
    """Fill insertions/deletions stats from git diff --numstat."""
    try:
        numstat = repo.git.diff(commit_a.hexsha, commit_b.hexsha, numstat=True)
    except Exception:
        return

    stats_by_path: dict[str, tuple[int, int]] = {}
    for line in numstat.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        ins_str, del_str, raw_path = parts
        try:
            ins = int(ins_str) if ins_str != "-" else 0
            dels = int(del_str) if del_str != "-" else 0
        except ValueError:
            continue
        for path in _parse_numstat_path(raw_path):
            stats_by_path[path] = (ins, dels)

    for fc in changes:
        if fc.path in stats_by_path:
            fc.insertions, fc.deletions = stats_by_path[fc.path]
        elif fc.old_path and fc.old_path in stats_by_path:
            fc.insertions, fc.deletions = stats_by_path[fc.old_path]


def count_diff_lines(diff_text: str) -> int:
    """Count the number of added/removed lines in a unified diff.

    Only counts lines starting with + or - (excluding --- and +++ headers).
    """
    count = 0
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            count += 1
        elif line.startswith("-") and not line.startswith("---"):
            count += 1
    return count
