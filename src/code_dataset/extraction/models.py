"""Data models for extracted merge information."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MergeType(str, Enum):
    """Type of merge detected in git history."""

    MERGE_COMMIT = "merge_commit"
    SQUASH = "squash"


@dataclass
class FileChange:
    """A single file changed in a merge."""

    path: str
    old_path: str | None = None  # Set if file was renamed
    content_before: str | None = None
    content_after: str | None = None
    insertions: int = 0
    deletions: int = 0
    is_binary: bool = False
    is_new: bool = False
    is_deleted: bool = False


@dataclass
class CommitInfo:
    """Information about a single commit on a branch."""

    sha: str
    message: str
    author: str
    author_email: str
    timestamp: datetime


@dataclass
class MergeRecord:
    """A single extracted merge/PR from git history."""

    id: str  # "{repo_name}/{merge_sha_short}"
    repo_name: str
    merge_sha: str
    merge_type: MergeType
    merge_message: str
    branch_name: str
    diff: str  # Full unified diff
    files_changed: list[FileChange] = field(default_factory=list)
    branch_commits: list[CommitInfo] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    timestamp: datetime | None = None
    merge_base_sha: str = ""
    insertions: int = 0
    deletions: int = 0
    repo_tree: str = ""  # Abbreviated repo structure

    # Enrichment fields (filled in Stage 3)
    title: str = ""
    description: str = ""
    change_type: str = ""
    difficulty: str = ""
    languages: list[str] = field(default_factory=list)
    description_source: str = ""  # "original" | "synthetic"
    quality_score: float = -1.0

    @property
    def num_files(self) -> int:
        return len(self.files_changed)

    @property
    def diff_lines(self) -> int:
        return self.diff.count("\n")

    @property
    def file_paths(self) -> list[str]:
        return [f.path for f in self.files_changed]

    @property
    def combined_commit_messages(self) -> str:
        return "\n".join(c.message for c in self.branch_commits)

    @property
    def has_test_changes(self) -> bool:
        test_patterns = ("test_", "_test.", ".test.", "tests/", "spec/", "_spec.")
        return any(any(p in f.path.lower() for p in test_patterns) for f in self.files_changed)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "repo_name": self.repo_name,
            "merge_sha": self.merge_sha,
            "merge_type": self.merge_type.value,
            "merge_message": self.merge_message,
            "branch_name": self.branch_name,
            "diff": self.diff,
            "files_changed": [
                {
                    "path": f.path,
                    "old_path": f.old_path,
                    "content_before": f.content_before,
                    "content_after": f.content_after,
                    "insertions": f.insertions,
                    "deletions": f.deletions,
                    "is_binary": f.is_binary,
                    "is_new": f.is_new,
                    "is_deleted": f.is_deleted,
                }
                for f in self.files_changed
            ],
            "branch_commits": [
                {
                    "sha": c.sha,
                    "message": c.message,
                    "author": c.author,
                    "author_email": c.author_email,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in self.branch_commits
            ],
            "authors": self.authors,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "merge_base_sha": self.merge_base_sha,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "num_files": self.num_files,
            "diff_lines": self.diff_lines,
            "has_test_changes": self.has_test_changes,
            "title": self.title,
            "description": self.description,
            "change_type": self.change_type,
            "difficulty": self.difficulty,
            "languages": self.languages,
            "description_source": self.description_source,
            "quality_score": self.quality_score,
            "repo_tree": self.repo_tree,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MergeRecord:
        """Deserialize from a dict (e.g., from JSONL)."""
        files = [
            FileChange(
                path=f["path"],
                old_path=f.get("old_path"),
                content_before=f.get("content_before"),
                content_after=f.get("content_after"),
                insertions=f.get("insertions", 0),
                deletions=f.get("deletions", 0),
                is_binary=f.get("is_binary", False),
                is_new=f.get("is_new", False),
                is_deleted=f.get("is_deleted", False),
            )
            for f in data.get("files_changed", [])
        ]
        commits = [
            CommitInfo(
                sha=c["sha"],
                message=c["message"],
                author=c["author"],
                author_email=c["author_email"],
                timestamp=datetime.fromisoformat(c["timestamp"]),
            )
            for c in data.get("branch_commits", [])
        ]
        ts = data.get("timestamp")
        return cls(
            id=data["id"],
            repo_name=data["repo_name"],
            merge_sha=data["merge_sha"],
            merge_type=MergeType(data["merge_type"]),
            merge_message=data["merge_message"],
            branch_name=data.get("branch_name", ""),
            diff=data["diff"],
            files_changed=files,
            branch_commits=commits,
            authors=data.get("authors", []),
            timestamp=datetime.fromisoformat(ts) if ts else None,
            merge_base_sha=data.get("merge_base_sha", ""),
            insertions=data.get("insertions", 0),
            deletions=data.get("deletions", 0),
            repo_tree=data.get("repo_tree", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            change_type=data.get("change_type", ""),
            difficulty=data.get("difficulty", ""),
            languages=data.get("languages", []),
            description_source=data.get("description_source", ""),
            quality_score=data.get("quality_score", -1.0),
        )
