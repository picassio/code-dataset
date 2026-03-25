"""Detect squash-merged commits on a main branch.

Squash merges compress an entire feature branch into a single commit.
They are harder to detect than merge commits since there are no structural
clues (no second parent). We use heuristics:

1. Multi-line commit messages (squash often includes branch commit summaries)
2. PR number patterns like (#123) in the commit title
3. Unusually large diffs relative to surrounding commits
4. Keywords like "squash", "merge", or a list of bullet points
"""

from __future__ import annotations

import logging
import re

from git import Commit, Repo

logger = logging.getLogger(__name__)

# Patterns that suggest a squash merge
_PR_NUMBER_PATTERN = re.compile(r"\(#\d+\)")
_SQUASH_KEYWORDS = re.compile(r"(?i)(?:squash|merge|merged)\b")
_BULLET_PATTERN = re.compile(r"^\s*[-*]\s+", re.MULTILINE)


def _squash_score(commit: Commit) -> float:
    """Score how likely a commit is a squash merge (0.0 to 1.0).

    Returns a confidence score based on heuristic signals.
    """
    msg = commit.message.strip()
    lines = msg.split("\n")
    score = 0.0

    # PR number in title: strong signal
    if _PR_NUMBER_PATTERN.search(lines[0]):
        score += 0.4

    # Multi-line commit message with blank line separator
    body_lines = [line for line in lines[2:] if line.strip()] if len(lines) > 2 else []
    if len(body_lines) >= 2:
        score += 0.2

    # Bullet points in body (common in squash summaries)
    bullet_count = len(_BULLET_PATTERN.findall(msg))
    if bullet_count >= 2:
        score += 0.2

    # Keywords
    if _SQUASH_KEYWORDS.search(msg):
        score += 0.1

    # Large diff (checked by caller, not here — this is message-only scoring)

    return min(score, 1.0)


def find_squash_merges(
    repo: Repo,
    main_branch: str = "main",
    since: str | None = None,
    until: str | None = None,
    min_score: float = 0.3,
    exclude_merge_commits: bool = True,
) -> list[Commit]:
    """Find likely squash-merged commits on the main branch.

    Args:
        repo: GitPython Repo instance.
        main_branch: Name of the main branch.
        since: Optional ISO date string filter.
        until: Optional ISO date string filter.
        min_score: Minimum squash-likelihood score (0.0–1.0).
        exclude_merge_commits: Skip commits that are actual merge commits.

    Returns:
        List of commits likely to be squash merges, newest first.
    """
    log_kwargs: dict = {"first_parent": True}
    if since:
        log_kwargs["after"] = since
    if until:
        log_kwargs["before"] = until

    try:
        branch_ref = repo.refs[main_branch]  # type: ignore[index]
    except (IndexError, KeyError):
        try:
            branch_ref = repo.commit(main_branch)
        except Exception:
            logger.error("Branch %r not found in repository", main_branch)
            return []

    squashes: list[Commit] = []
    for commit in repo.iter_commits(branch_ref, **log_kwargs):
        # Skip actual merge commits
        if exclude_merge_commits and len(commit.parents) >= 2:
            continue

        # Skip commits with no parent (initial commit)
        if not commit.parents:
            continue

        score = _squash_score(commit)
        if score >= min_score:
            squashes.append(commit)

    logger.info(
        "Found %d likely squash merges on %s (threshold=%.1f)",
        len(squashes),
        main_branch,
        min_score,
    )
    return squashes


def parse_squash_branch_name(commit_message: str) -> str:
    """Try to extract a branch name from a squash merge commit message.

    Squash commit messages often don't contain the branch name explicitly,
    but some forges add it. We try common patterns.

    Args:
        commit_message: The squash commit message.

    Returns:
        Extracted branch name, or empty string.
    """
    first_line = commit_message.strip().split("\n")[0]

    # "Feature: add user auth (#123)" → "feature/add-user-auth"
    # Remove PR number
    cleaned = _PR_NUMBER_PATTERN.sub("", first_line).strip()
    if cleaned:
        # Convert title to slug-like branch name
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", cleaned).strip("-").lower()
        if slug:
            return slug

    return ""
