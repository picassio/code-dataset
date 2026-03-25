"""Core git extraction: extract merge records from a local repository.

Supports both merge commits and squash merges. Outputs MergeRecord objects
with full diffs, file contents, and metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from git import Commit, Repo

from ..config import Config
from .context_builder import build_repo_tree
from .diff_parser import count_diff_lines, get_diff_text, get_file_changes
from .merge_detector import find_merge_commits, get_branch_commits, get_merge_base, parse_branch_name
from .models import CommitInfo, MergeRecord, MergeType
from .squash_detector import find_squash_merges, parse_squash_branch_name

logger = logging.getLogger(__name__)


def _commit_datetime(commit: Commit) -> datetime:
    """Get commit authored datetime as timezone-aware."""
    return datetime.fromtimestamp(commit.authored_date, tz=timezone.utc)


def _commit_info(commit: Commit) -> CommitInfo:
    """Convert a git Commit to our CommitInfo model."""
    return CommitInfo(
        sha=commit.hexsha,
        message=commit.message.strip(),
        author=str(commit.author),
        author_email=str(commit.author.email) if commit.author.email else "",
        timestamp=_commit_datetime(commit),
    )


def extract_merge_commit(
    repo: Repo,
    merge_commit: Commit,
    repo_name: str,
    config: Config,
) -> MergeRecord | None:
    """Extract a MergeRecord from a merge commit.

    Args:
        repo: GitPython Repo instance.
        merge_commit: A commit with >= 2 parents.
        repo_name: Name of the repository.
        config: Application config.

    Returns:
        MergeRecord if extraction succeeds, None otherwise.
    """
    merge_base = get_merge_base(repo, merge_commit)
    if merge_base is None:
        logger.debug("Skipping merge %s: no merge base found", merge_commit.hexsha[:8])
        return None

    branch_tip = merge_commit.parents[1]  # Second parent = branch tip

    # Get diff
    diff_text = get_diff_text(repo, merge_base, branch_tip)
    if not diff_text.strip():
        logger.debug("Skipping merge %s: empty diff", merge_commit.hexsha[:8])
        return None

    # Check diff size
    diff_line_count = count_diff_lines(diff_text)
    if diff_line_count < config.min_diff_lines:
        logger.debug("Skipping merge %s: diff too small (%d lines)", merge_commit.hexsha[:8], diff_line_count)
        return None
    if diff_line_count > config.max_diff_lines:
        logger.debug("Skipping merge %s: diff too large (%d lines)", merge_commit.hexsha[:8], diff_line_count)
        return None

    # Get file changes
    file_changes = get_file_changes(
        repo,
        merge_base,
        branch_tip,
        include_content=config.include_file_contents,
        max_file_size_kb=config.max_file_size_kb,
    )

    # Get branch commits
    branch_commits = get_branch_commits(repo, merge_base, branch_tip)
    commit_infos = [_commit_info(c) for c in branch_commits]

    # Parse branch name
    branch_name = parse_branch_name(merge_commit.message)

    # Collect unique authors
    authors = list({c.author for c in commit_infos})

    # Compute total stats
    total_ins = sum(f.insertions for f in file_changes)
    total_del = sum(f.deletions for f in file_changes)

    # Build repo tree
    repo_tree = ""
    if config.include_repo_tree:
        repo_tree = build_repo_tree(repo, merge_commit)

    return MergeRecord(
        id=f"{repo_name}/{merge_commit.hexsha[:12]}",
        repo_name=repo_name,
        merge_sha=merge_commit.hexsha,
        merge_type=MergeType.MERGE_COMMIT,
        merge_message=merge_commit.message.strip(),
        branch_name=branch_name,
        diff=diff_text,
        files_changed=file_changes,
        branch_commits=commit_infos,
        authors=authors,
        timestamp=_commit_datetime(merge_commit),
        merge_base_sha=merge_base.hexsha,
        insertions=total_ins,
        deletions=total_del,
        repo_tree=repo_tree,
    )


def extract_squash_commit(
    repo: Repo,
    commit: Commit,
    repo_name: str,
    config: Config,
) -> MergeRecord | None:
    """Extract a MergeRecord from a squash-merged commit.

    Args:
        repo: GitPython Repo instance.
        commit: A single-parent commit suspected to be a squash merge.
        repo_name: Name of the repository.
        config: Application config.

    Returns:
        MergeRecord if extraction succeeds, None otherwise.
    """
    parent = commit.parents[0]

    # Get diff
    diff_text = get_diff_text(repo, parent, commit)
    if not diff_text.strip():
        return None

    # Check diff size
    diff_line_count = count_diff_lines(diff_text)
    if diff_line_count < config.min_diff_lines:
        return None
    if diff_line_count > config.max_diff_lines:
        return None

    # Get file changes
    file_changes = get_file_changes(
        repo,
        parent,
        commit,
        include_content=config.include_file_contents,
        max_file_size_kb=config.max_file_size_kb,
    )

    # Parse branch name from message
    branch_name = parse_squash_branch_name(commit.message)

    # Total stats
    total_ins = sum(f.insertions for f in file_changes)
    total_del = sum(f.deletions for f in file_changes)

    # Build repo tree
    repo_tree = ""
    if config.include_repo_tree:
        repo_tree = build_repo_tree(repo, commit)

    return MergeRecord(
        id=f"{repo_name}/{commit.hexsha[:12]}",
        repo_name=repo_name,
        merge_sha=commit.hexsha,
        merge_type=MergeType.SQUASH,
        merge_message=commit.message.strip(),
        branch_name=branch_name,
        diff=diff_text,
        files_changed=file_changes,
        branch_commits=[_commit_info(commit)],
        authors=[str(commit.author)],
        timestamp=_commit_datetime(commit),
        merge_base_sha=parent.hexsha,
        insertions=total_ins,
        deletions=total_del,
        repo_tree=repo_tree,
    )


def extract_repo(
    repo_path: str | Path,
    repo_name: str | None = None,
    main_branch: str = "main",
    config: Config | None = None,
) -> list[MergeRecord]:
    """Extract all merge records from a repository.

    Args:
        repo_path: Path to the local git repository.
        repo_name: Name for the repo (defaults to folder name).
        main_branch: Name of the main branch.
        config: Application config (uses defaults if None).

    Returns:
        List of extracted MergeRecords.
    """
    repo_path = Path(repo_path).expanduser().resolve()
    if not (repo_path / ".git").exists() and not repo_path.name == ".git":
        raise ValueError(f"Not a git repository: {repo_path}")

    if config is None:
        config = Config()

    if repo_name is None:
        repo_name = repo_path.name

    repo = Repo(str(repo_path))
    strategy = config.merge_strategy
    records: list[MergeRecord] = []

    logger.info("Extracting from %s (branch=%s, strategy=%s)", repo_path, main_branch, strategy)

    # Extract merge commits
    if strategy in ("auto", "merge_commit", "all"):
        merges = find_merge_commits(
            repo,
            main_branch,
            since=config.extraction_since,
            until=config.extraction_until,
        )
        for mc in merges:
            record = extract_merge_commit(repo, mc, repo_name, config)
            if record:
                records.append(record)
        logger.info("Extracted %d merge commit records", len(records))

    # Extract squash merges
    squash_start = len(records)
    if strategy in ("auto", "squash", "all"):
        squashes = find_squash_merges(
            repo,
            main_branch,
            since=config.extraction_since,
            until=config.extraction_until,
        )
        for sc in squashes:
            record = extract_squash_commit(repo, sc, repo_name, config)
            if record:
                records.append(record)
        logger.info("Extracted %d squash merge records", len(records) - squash_start)

    logger.info("Total extracted: %d records from %s", len(records), repo_name)
    return records


def write_records(records: list[MergeRecord], output_path: Path) -> None:
    """Write merge records to a JSONL file.

    Args:
        records: List of MergeRecords to write.
        output_path: Path to the output JSONL file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False))
            f.write("\n")
    logger.info("Wrote %d records to %s", len(records), output_path)


def read_records(input_path: Path) -> list[MergeRecord]:
    """Read merge records from a JSONL file.

    Args:
        input_path: Path to the JSONL file.

    Returns:
        List of MergeRecords.
    """
    records: list[MergeRecord] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                records.append(MergeRecord.from_dict(data))
    logger.info("Read %d records from %s", len(records), input_path)
    return records
