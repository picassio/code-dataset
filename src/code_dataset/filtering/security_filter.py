"""Detect and redact secrets, API keys, and PII in code diffs.

Uses regex patterns to detect common secret formats. For edge cases,
an optional LLM-based check can be enabled via DSPy.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Compiled regex patterns for common secret formats
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # API keys — order matters: more specific patterns first
    (re.compile(r"sk-ant-api[a-zA-Z0-9-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"sk-ant-oat[a-zA-Z0-9-]{20,}"), "[REDACTED_ANTHROPIC_OAUTH]"),
    (re.compile(r"sk-or-v1-[a-zA-Z0-9]{20,}"), "[REDACTED_OPENROUTER]"),
    (re.compile(r"sk-proj-[a-zA-Z0-9_-]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"gsk_[a-zA-Z0-9]{20,}"), "[REDACTED_GROQ]"),
    (re.compile(r"AIza[a-zA-Z0-9_-]{35}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"gho_[a-zA-Z0-9]{36}"), "[REDACTED_GITHUB_OAUTH]"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{22,}"), "[REDACTED_GITHUB_PAT_V2]"),
    (re.compile(r"glpat-[a-zA-Z0-9_-]{20,}"), "[REDACTED_GITLAB_PAT]"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"xox[bporas]-[a-zA-Z0-9-]{10,}"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[a-zA-Z0-9]+"), "[REDACTED_SLACK_WEBHOOK]"),
    (re.compile(r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}"), "[REDACTED_SENDGRID]"),
    (re.compile(r"sq0[a-z]{3}-[a-zA-Z0-9_-]{22,}"), "[REDACTED_SQUARE]"),
    # Generic patterns
    (
        re.compile(
            r"(?i)(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token)"
            r"\s*[:=]\s*['\"]([a-zA-Z0-9_\-/.+=]{20,})['\"]"
        ),
        "[REDACTED_GENERIC_SECRET]",
    ),
    (re.compile(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"), "[REDACTED_PASSWORD]"),
    # Private keys
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"), "[REDACTED_SSH_KEY]"),
]

# PII patterns
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Email addresses (but not common examples)
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "EMAIL"),
    # Phone numbers (US format)
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "PHONE"),
    # SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN"),
    # Credit card numbers (basic)
    (re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "CREDIT_CARD"),
]

# Common example/test values to not flag
_FALSE_POSITIVE_EMAILS = {
    "user@example.com",
    "test@test.com",
    "admin@localhost",
    "noreply@github.com",
    "name@email.com",
    "you@example.com",
    "your-email@example.com",
    "email@example.com",
}


def scan_secrets(text: str) -> list[dict[str, str]]:
    """Scan text for leaked secrets.

    Args:
        text: Text to scan (typically a diff).

    Returns:
        List of findings, each with 'pattern', 'match', and 'replacement' keys.
    """
    findings: list[dict[str, str]] = []
    for pattern, replacement in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                {
                    "pattern": replacement,
                    "match": match.group()[:20] + "...",
                    "replacement": replacement,
                }
            )
    return findings


def scan_pii(text: str) -> list[dict[str, str]]:
    """Scan text for PII.

    Args:
        text: Text to scan.

    Returns:
        List of PII findings with 'type' and 'match' keys.
    """
    findings: list[dict[str, str]] = []
    for pattern, pii_type in _PII_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group()
            # Skip known false positives
            if pii_type == "EMAIL" and value.lower() in _FALSE_POSITIVE_EMAILS:
                continue
            findings.append(
                {
                    "type": pii_type,
                    "match": value[:20] + "..." if len(value) > 20 else value,
                }
            )
    return findings


def redact_secrets(text: str) -> str:
    """Redact all detected secrets from text.

    Args:
        text: Text containing potential secrets.

    Returns:
        Text with secrets replaced by redaction markers.
    """
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def is_safe(text: str) -> bool:
    """Check if text is safe (no secrets or PII detected).

    Args:
        text: Text to check.

    Returns:
        True if no secrets or PII found.
    """
    return not scan_secrets(text) and not scan_pii(text)
