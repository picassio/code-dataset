"""Detect merge commits in a git repository."""

from __future__ import annotations

import logging
import re

from git import Commit, Repo

logger = logging.getLogger(__name__)

# Pattern for extracting branch name from merge commit messages
_MERGE_PATTERNS = [
    re.compile(r"Merge pull request #\d+ from (?:[\w.-]+/)?(.+)"),
    re.compile(r"Merge branch '(.+?)' into .+"),
    re.compile(r"Merge branch '(.+?)'"),
    re.compile(r"Merge remote-tracking branch '.+?/(.+?)'"),
    re.compile(r"Merge (.+?) into .+"),
]


def parse_branch_name(merge_message: str) -> str:
    """Extract branch name from a merge commit message.

    Args:
        merge_message: The merge commit message.

    Returns:
        Extracted branch name, or empty string if not found.
    """
    for pattern in _MERGE_PATTERNS:
        match = pattern.match(merge_message.strip().split("\n")[0])
        if match:
            return match.group(1).strip()
    return ""


def find_merge_commits(
    repo: Repo,
    main_branch: str = "main",
    since: str | None = None,
    until: str | None = None,
) -> list[Commit]:
    """Find all merge commits on the main branch.

    A merge commit is a commit with two or more parents.

    Args:
        repo: GitPython Repo instance.
        main_branch: Name of the main branch (e.g., "main", "master").
        since: Optional ISO date string to filter commits after this date.
        until: Optional ISO date string to filter commits before this date.

    Returns:
        List of merge Commit objects, newest first.
    """
    log_kwargs: dict = {"first_parent": True}

    if since:
        log_kwargs["after"] = since
    if until:
        log_kwargs["before"] = until

    try:
        branch_ref = repo.refs[main_branch]  # type: ignore[index]
    except (IndexError, KeyError):
        # Try as a plain revision
        try:
            branch_ref = repo.commit(main_branch)
        except Exception:
            logger.error("Branch %r not found in repository", main_branch)
            return []

    merges: list[Commit] = []
    for commit in repo.iter_commits(branch_ref, **log_kwargs):
        if len(commit.parents) >= 2:
            merges.append(commit)

    logger.info("Found %d merge commits on %s", len(merges), main_branch)
    return merges


def get_merge_base(repo: Repo, merge_commit: Commit) -> Commit | None:
    """Get the merge base for a merge commit.

    The merge base is the common ancestor of the two parents.

    Args:
        repo: GitPython Repo instance.
        merge_commit: A merge commit with >= 2 parents.

    Returns:
        The merge base commit, or None if it cannot be determined.
    """
    if len(merge_commit.parents) < 2:
        return None

    try:
        bases = repo.merge_base(merge_commit.parents[0], merge_commit.parents[1])
        if bases:
            return bases[0]
    except Exception as e:
        logger.warning("Failed to find merge base for %s: %s", merge_commit.hexsha[:8], e)

    return None


def get_branch_commits(repo: Repo, merge_base: Commit, branch_tip: Commit) -> list[Commit]:
    """Get all commits on a branch between merge_base and branch_tip.

    Args:
        repo: GitPython Repo instance.
        merge_base: The merge base commit.
        branch_tip: The tip of the branch (second parent of merge commit).

    Returns:
        List of commits on the branch, oldest first.
    """
    try:
        rev_range = f"{merge_base.hexsha}..{branch_tip.hexsha}"
        commits = list(repo.iter_commits(rev_range))
        commits.reverse()  # oldest first
        return commits
    except Exception as e:
        logger.warning("Failed to get branch commits: %s", e)
        return []
