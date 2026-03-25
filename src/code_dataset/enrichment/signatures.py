"""DSPy Signatures for structured LLM extraction.

These signatures define the exact input/output schema for each LLM call.
DSPy guarantees typed, structured output — no free-form text parsing.
"""

from __future__ import annotations

import dspy


class MergeDescription(dspy.Signature):
    """Analyze a code diff and reverse-engineer the task or issue that produced it.

    You are given a unified diff from a code repository along with commit messages
    and branch name. Write a clear, actionable developer task description that would
    lead someone to produce these exact changes. Focus on the intent (what and why),
    not just the mechanics (what files changed).
    """

    diff: str = dspy.InputField(desc="Unified diff of all code changes in this merge")
    branch_name: str = dspy.InputField(desc="Git branch name if available, else empty string")
    commit_messages: str = dspy.InputField(desc="All commit messages on the branch, newline-separated")
    file_list: str = dspy.InputField(desc="List of changed files, newline-separated")

    title: str = dspy.OutputField(desc="One-line task title (imperative mood, e.g., 'Add retry logic to HTTP client')")
    description: str = dspy.OutputField(desc="2-5 sentence task description explaining what needs to be done and why")
    change_type: str = dspy.OutputField(desc="Exactly one of: bugfix, feature, refactor, test, docs, chore")
    difficulty: str = dspy.OutputField(desc="Exactly one of: easy, medium, hard")
    languages: list[str] = dspy.OutputField(desc="Programming languages involved (e.g., ['python', 'typescript'])")


class DescriptionQuality(dspy.Signature):
    """Evaluate whether a commit or merge description is good enough to use as
    a training data instruction for fine-tuning a code LLM.

    A good description clearly states what needs to be done (the task) and ideally why.
    A poor description is vague, too short, or just references internal jargon without
    explaining the actual change.
    """

    description: str = dspy.InputField(desc="The commit/PR description to evaluate")
    diff_summary: str = dspy.InputField(
        desc="Summary of the code change: number of files, insertions, deletions, file names"
    )

    quality_score: float = dspy.OutputField(
        desc="Quality score from 0.0 (completely useless, e.g., 'fix') to 1.0 (excellent task description)"
    )
    is_instructive: bool = dspy.OutputField(
        desc="True if this description could serve as a task instruction for another developer"
    )
    reason: str = dspy.OutputField(desc="One-sentence explanation of the quality assessment")


class DiffClassifier(dspy.Signature):
    """Classify a code diff by change type and difficulty level.

    Analyze the diff to determine what kind of change it is and how complex
    the work would be for a developer to implement from scratch.
    """

    diff: str = dspy.InputField(desc="Unified diff of code changes")
    file_list: str = dspy.InputField(desc="Files changed, newline-separated")

    change_type: str = dspy.OutputField(desc="Exactly one of: bugfix, feature, refactor, test, docs, chore")
    difficulty: str = dspy.OutputField(desc="Exactly one of: easy, medium, hard")
    summary: str = dspy.OutputField(desc="One-line summary of what this change does")


class SecurityCheck(dspy.Signature):
    """Check a code diff for leaked secrets, API keys, passwords, or PII.

    Examine the diff carefully for any hardcoded credentials, API keys, tokens,
    private keys, passwords, or personally identifiable information that should
    not be included in a public training dataset.
    """

    diff: str = dspy.InputField(desc="Code diff to check for sensitive data")

    has_secrets: bool = dspy.OutputField(desc="True if API keys, tokens, passwords, or private keys are found")
    has_pii: bool = dspy.OutputField(desc="True if personal information (emails, phone numbers, SSNs) is found")
    findings: list[str] = dspy.OutputField(desc="Description of each finding (empty list if none)")
    safe_to_use: bool = dspy.OutputField(desc="True if the diff is safe to include in a training dataset")
