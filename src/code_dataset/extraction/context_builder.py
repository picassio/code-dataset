"""Build repository context for extracted merges."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from git import Commit, Repo, Tree

logger = logging.getLogger(__name__)

# Maximum depth for tree display
_MAX_TREE_DEPTH = 4
_MAX_ENTRIES_PER_LEVEL = 30


def build_repo_tree(repo: Repo, at_commit: Commit, max_depth: int = _MAX_TREE_DEPTH) -> str:
    """Build an abbreviated directory tree of the repository at a given commit.

    Args:
        repo: GitPython Repo instance.
        at_commit: Commit to snapshot the tree from.
        max_depth: Maximum directory depth to traverse.

    Returns:
        A string representation of the repo directory tree.
    """
    try:
        tree = at_commit.tree
    except Exception as e:
        logger.warning("Failed to get tree at %s: %s", at_commit.hexsha[:8], e)
        return ""

    lines: list[str] = []
    _walk_tree(tree, "", 0, max_depth, lines)
    return "\n".join(lines)


def _walk_tree(
    tree: Tree,
    prefix: str,
    depth: int,
    max_depth: int,
    lines: list[str],
) -> None:
    """Recursively walk a git tree and build directory listing."""
    if depth >= max_depth:
        return

    entries = sorted(tree.traverse(depth=1), key=lambda e: (e.type != "tree", e.name))
    shown = 0

    for entry in entries:
        if shown >= _MAX_ENTRIES_PER_LEVEL:
            remaining = len(entries) - shown
            if remaining > 0:
                lines.append(f"{prefix}... ({remaining} more)")
            break

        if entry.type == "tree":
            lines.append(f"{prefix}{entry.name}/")
            _walk_tree(entry, prefix + "  ", depth + 1, max_depth, lines)
        else:
            lines.append(f"{prefix}{entry.name}")
        shown += 1


def get_related_files(
    repo: Repo,
    at_commit: Commit,
    changed_files: list[str],
    max_file_size_kb: int = 100,
) -> dict[str, str]:
    """Get content of files related to the changed files.

    Related files are in the same directories as changed files. This helps
    provide context for understanding the changes.

    Args:
        repo: GitPython Repo instance.
        at_commit: Commit to read files from.
        changed_files: List of file paths that were changed.
        max_file_size_kb: Maximum file size to include.

    Returns:
        Dict mapping file path to content.
    """
    # Collect directories of changed files
    dirs: set[str] = set()
    for f in changed_files:
        parent = str(PurePosixPath(f).parent)
        if parent != ".":
            dirs.add(parent)

    related: dict[str, str] = {}
    changed_set = set(changed_files)

    try:
        tree = at_commit.tree
    except Exception:
        return related

    for dir_path in dirs:
        try:
            subtree = tree[dir_path]
            if subtree.type != "tree":
                continue
            for blob in subtree.blobs:
                full_path = f"{dir_path}/{blob.name}"
                if full_path in changed_set:
                    continue  # Skip already-changed files
                if blob.size > max_file_size_kb * 1024:
                    continue
                try:
                    content = blob.data_stream.read().decode("utf-8", errors="replace")
                    related[full_path] = content
                except Exception:
                    continue
        except (KeyError, Exception):
            continue

    return related
