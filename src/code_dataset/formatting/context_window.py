"""Smart context window management for dataset formatting.

Selects and truncates file contents to fit within a token budget,
prioritizing changed files and their immediate neighbors.
"""

from __future__ import annotations

import logging

from ..extraction.models import MergeRecord

logger = logging.getLogger(__name__)

# Approximate characters per token (conservative estimate)
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string.

    Uses a simple character-based heuristic (4 chars ≈ 1 token).
    Good enough for context budgeting; not for billing.
    """
    return len(text) // _CHARS_PER_TOKEN


def truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a token budget.

    Tries to cut at line boundaries. Adds truncation notice.
    """
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars * 0.7:
        truncated = truncated[:last_newline]

    remaining_lines = text[len(truncated) :].count("\n")
    truncated += f"\n... [{remaining_lines} lines truncated]"
    return truncated


def build_context(record: MergeRecord, max_tokens: int = 8192) -> dict[str, str]:
    """Build a context dict of file contents within a token budget.

    Prioritizes:
    1. Changed files (content_before)
    2. Smaller files first (more files in context)

    Args:
        record: The merge record.
        max_tokens: Maximum total tokens for all file contents.

    Returns:
        Dict mapping file path → file content (before state).
    """
    budget = max_tokens
    context: dict[str, str] = {}

    # Sort by size (smaller first to fit more files)
    files_with_content = [f for f in record.files_changed if f.content_before and not f.is_binary]
    files_with_content.sort(key=lambda f: len(f.content_before or ""))

    for fc in files_with_content:
        content = fc.content_before or ""
        tokens = estimate_tokens(content)

        if tokens > budget:
            # Try to fit a truncated version
            if budget > 200:  # Only if we have meaningful space left
                content = truncate_to_budget(content, budget)
                context[fc.path] = content
            break

        context[fc.path] = content
        budget -= tokens

    return context


def build_response_files(record: MergeRecord) -> dict[str, str]:
    """Build the response file contents (after state).

    Args:
        record: The merge record.

    Returns:
        Dict mapping file path → file content (after state).
    """
    files: dict[str, str] = {}
    for fc in record.files_changed:
        if fc.content_after and not fc.is_binary:
            files[fc.path] = fc.content_after
        elif fc.is_deleted:
            files[fc.path] = ""  # Explicitly mark deleted
    return files
