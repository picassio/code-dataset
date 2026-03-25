"""RL (Reinforcement Learning) dataset formatter.

Produces records suitable for GRPO/PPO training where the reward signal
comes from test execution. Only includes merges that modify test files,
since tests are the verifiable reward.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ..extraction.models import MergeRecord
from .context_window import build_context

logger = logging.getLogger(__name__)

# Common test runner commands by language/framework
_TEST_COMMANDS: dict[str, str] = {
    "python": "pytest",
    "javascript": "npm test",
    "typescript": "npm test",
    "java": "mvn test",
    "go": "go test ./...",
    "rust": "cargo test",
    "ruby": "bundle exec rspec",
    "php": "phpunit",
    "csharp": "dotnet test",
}

# Test file patterns
_TEST_PATTERNS = [
    re.compile(r"test_[\w]+\.py$"),
    re.compile(r"[\w]+_test\.py$"),
    re.compile(r"[\w]+_test\.go$"),
    re.compile(r"[\w]+\.test\.(ts|tsx|js|jsx)$"),
    re.compile(r"[\w]+\.spec\.(ts|tsx|js|jsx)$"),
    re.compile(r"tests?/"),
    re.compile(r"spec/"),
    re.compile(r"__tests__/"),
    re.compile(r"Test[\w]+\.java$"),
    re.compile(r"[\w]+Test\.java$"),
]


def _is_test_file(path: str) -> bool:
    """Check if a file path is a test file."""
    return any(p.search(path) for p in _TEST_PATTERNS)


def _guess_test_command(record: MergeRecord) -> str:
    """Guess the test command based on file types and languages."""
    for lang in record.languages:
        lang_lower = lang.lower()
        if lang_lower in _TEST_COMMANDS:
            return _TEST_COMMANDS[lang_lower]

    # Infer from file extensions
    extensions = {Path(f.path).suffix.lower() for f in record.files_changed}
    if ".py" in extensions:
        return "pytest"
    if ".ts" in extensions or ".js" in extensions:
        return "npm test"
    if ".go" in extensions:
        return "go test ./..."
    if ".rs" in extensions:
        return "cargo test"
    if ".java" in extensions:
        return "mvn test"

    return "pytest"  # Default fallback


def format_rl_record(record: MergeRecord, max_context_tokens: int = 8192) -> dict | None:
    """Format a single merge record as an RL training example.

    Only produces output for records that include test changes, since
    tests serve as the verifiable reward signal.

    Args:
        record: Enriched merge record.
        max_context_tokens: Token budget for codebase snapshot.

    Returns:
        Dict in RL format, or None if no test changes.
    """
    if not record.has_test_changes:
        return None

    # Separate test and implementation files
    test_files = [f for f in record.files_changed if _is_test_file(f.path)]
    impl_files = [f for f in record.files_changed if not _is_test_file(f.path)]

    if not test_files or not impl_files:
        return None  # Need both test and implementation changes

    # Build prompt: task description + test file changes
    instruction = record.title
    if record.description:
        instruction = f"{record.title}\n\n{record.description}"

    test_diff_parts = []
    for tf in test_files:
        # Include the test file content after (what tests need to pass)
        if tf.content_after:
            test_diff_parts.append(f"# {tf.path}\n{tf.content_after}")

    context_files = build_context(record, max_context_tokens)
    test_command = _guess_test_command(record)

    return {
        "id": f"{record.id}/rl",
        "prompt": instruction,
        "test_files": {tf.path: tf.content_after or "" for tf in test_files},
        "codebase_snapshot": context_files,
        "test_command": test_command,
        "gold_patch": record.diff,
        "metadata": {
            "repo_name": record.repo_name,
            "merge_sha": record.merge_sha,
            "num_test_files": len(test_files),
            "num_impl_files": len(impl_files),
            "change_type": record.change_type,
            "difficulty": record.difficulty,
            "languages": record.languages,
        },
    }


def write_rl_dataset(
    records: list[MergeRecord],
    output_path: Path,
    max_context_tokens: int = 8192,
) -> int:
    """Write an RL dataset to a JSONL file.

    Only includes records with test changes (verifiable reward).

    Args:
        records: Enriched merge records.
        output_path: Path to output JSONL file.
        max_context_tokens: Token budget.

    Returns:
        Number of records written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            entry = format_rl_record(record, max_context_tokens)
            if entry is None:
                continue
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")
            count += 1

    logger.info("Wrote %d RL records to %s", count, output_path)
    return count
