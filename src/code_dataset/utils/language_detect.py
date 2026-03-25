"""Programming language detection based on file extensions."""

from __future__ import annotations

from pathlib import Path

# Extension → language mapping
_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyx": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".m": "objective-c",
    ".mm": "objective-c",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".jl": "julia",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".hs": "haskell",
    ".lhs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".pl": "perl",
    ".pm": "perl",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".tex": "latex",
    ".tf": "terraform",
    ".hcl": "hcl",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".sol": "solidity",
    ".zig": "zig",
    ".nim": "nim",
    ".v": "v",
    ".cr": "crystal",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".cljc": "clojure",
    ".el": "emacs-lisp",
    ".vim": "vimscript",
    ".dockerfile": "dockerfile",
    ".cmake": "cmake",
    ".gradle": "gradle",
    ".groovy": "groovy",
}

# File name → language mapping (for files without extensions)
_FILENAME_MAP: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "CMakeLists.txt": "cmake",
    "Rakefile": "ruby",
    "Gemfile": "ruby",
    "Vagrantfile": "ruby",
    "Jenkinsfile": "groovy",
    "BUILD": "bazel",
    "WORKSPACE": "bazel",
}


def detect_language(file_path: str) -> str | None:
    """Detect the programming language of a file from its path.

    Args:
        file_path: File path (can be relative or absolute).

    Returns:
        Language name (lowercase) or None if unknown.
    """
    p = Path(file_path)

    # Check filename first
    if p.name in _FILENAME_MAP:
        return _FILENAME_MAP[p.name]

    # Check extension
    suffix = p.suffix.lower()
    if suffix in _EXTENSION_MAP:
        return _EXTENSION_MAP[suffix]

    return None


def detect_languages(file_paths: list[str]) -> list[str]:
    """Detect all programming languages in a list of file paths.

    Args:
        file_paths: List of file paths.

    Returns:
        Sorted list of unique detected languages.
    """
    languages: set[str] = set()
    for path in file_paths:
        lang = detect_language(path)
        if lang:
            languages.add(lang)
    return sorted(languages)
