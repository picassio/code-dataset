"""Configuration management for code-dataset.

Precedence (highest to lowest):
    1. CLI flags
    2. Environment variables (CODE_DATASET_* prefix)
    3. Project config.yaml (./config.yaml)
    4. Global config.yaml (~/.code-dataset/config.yaml)
    5. Built-in defaults

Secrets are loaded from .env files (never stored in config.yaml).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

GLOBAL_CONFIG_DIR = Path.home() / ".code-dataset"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.yaml"
GLOBAL_ENV_FILE = GLOBAL_CONFIG_DIR / ".env"

DEFAULTS: dict[str, Any] = {
    "llm": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "temperature": 0.3,
        "max_tokens": 4096,
        "num_retries": 3,
        "max_concurrent": 5,
        "max_calls": 500,
    },
    "extraction": {
        "merge_strategy": "auto",
        "min_diff_lines": 5,
        "max_diff_lines": 5000,
        "include_file_contents": True,
        "max_file_size_kb": 100,
        "since": None,
        "until": None,
    },
    "filtering": {
        "exclude_authors": [
            "dependabot[bot]",
            "renovate[bot]",
            "github-actions[bot]",
            "semantic-release-bot",
        ],
        "exclude_paths": [
            "*.lock",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "Pipfile.lock",
            "poetry.lock",
            "*.min.js",
            "*.min.css",
            "vendor/",
            "node_modules/",
            "dist/",
            ".git/",
        ],
        "exclude_extensions": [
            ".svg",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".mp3",
            ".mp4",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
        ],
        "min_commit_message_length": 10,
        "remove_secrets": True,
        "dedup": True,
    },
    "enrichment": {
        "generate_descriptions": True,
        "description_quality_threshold": 0.5,
        "classify_type": True,
        "classify_difficulty": True,
        "skip_if_enriched": True,
    },
    "output": {
        "dir": "./output",
        "mode": "separate",
        "formats": ["sft", "dpo", "rl"],
        "max_context_tokens": 8192,
        "include_repo_tree": True,
    },
    "logging": {
        "level": "INFO",
        "progress": True,
        "verbose": False,
        "file": None,
    },
}

ENV_MAPPINGS: dict[str, str] = {
    "llm.provider": "CODE_DATASET_PROVIDER",
    "llm.model": "CODE_DATASET_MODEL",
    "llm.temperature": "CODE_DATASET_TEMPERATURE",
    "llm.max_tokens": "CODE_DATASET_MAX_TOKENS",
    "llm.max_calls": "CODE_DATASET_MAX_CALLS",
    "llm.max_concurrent": "CODE_DATASET_MAX_CONCURRENT",
    "output.dir": "CODE_DATASET_OUTPUT_DIR",
    "output.mode": "CODE_DATASET_OUTPUT_MODE",
    "logging.level": "CODE_DATASET_LOG_LEVEL",
    "logging.verbose": "CODE_DATASET_VERBOSE",
}

ENV_TYPES: dict[str, type] = {
    "llm.temperature": float,
    "llm.max_tokens": int,
    "llm.max_calls": int,
    "llm.max_concurrent": int,
    "logging.verbose": bool,
}


def _cast_env_value(value: str, target_type: type) -> Any:
    """Cast a string environment variable to the target type."""
    if target_type is bool:
        return value.lower() in ("true", "1", "yes", "on")
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    return value


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    """Get a value from a nested dict using dotted key notation."""
    keys = dotted_key.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts. Override values take precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read and parse a YAML file safely."""
    try:
        content = path.read_text(encoding="utf-8")
        return yaml.safe_load(content) or {}
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read config file %s: %s", path, e)
        return {}


def _load_dotenv(path: Path) -> dict[str, str]:
    """Load environment variables from a .env file.

    Only sets variables not already in os.environ (existing env takes precedence).

    Returns:
        Dict of variable names to values that were loaded.
    """
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key.replace("_", "").replace("-", "").isalnum():
                if key not in os.environ:
                    os.environ[key] = value
                loaded[key] = value
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to load .env file %s: %s", path, e)

    return loaded


class Config:
    """Unified configuration with precedence chain.

    Precedence: CLI overrides > env vars > project YAML > global YAML > defaults.
    """

    def __init__(
        self,
        config_file: Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> None:
        self._cli = cli_overrides or {}
        self._load_env_files()
        self._file_config = self._load_yaml_chain(config_file)

    def _load_env_files(self) -> None:
        """Load .env files (project-level, then global)."""
        project_env = Path.cwd() / ".env"
        _load_dotenv(project_env)
        _load_dotenv(GLOBAL_ENV_FILE)

    def _load_yaml_chain(self, explicit: Path | None) -> dict[str, Any]:
        """Load and merge YAML config files in precedence order."""
        config: dict[str, Any] = {}
        if GLOBAL_CONFIG_FILE.exists():
            config = _deep_merge(config, _read_yaml(GLOBAL_CONFIG_FILE))
        project_config = Path.cwd() / "config.yaml"
        if project_config.exists():
            config = _deep_merge(config, _read_yaml(project_config))
        if explicit and explicit.exists() and explicit.resolve() != project_config.resolve():
            config = _deep_merge(config, _read_yaml(explicit))
        return config

    def _get(self, dotted_key: str, default: Any = None) -> Any:
        """Get config value with full precedence chain."""
        # 1. CLI override
        if dotted_key in self._cli:
            return self._cli[dotted_key]

        # 2. Environment variable
        env_var = ENV_MAPPINGS.get(dotted_key)
        if env_var:
            env_val = os.environ.get(env_var)
            if env_val is not None:
                target_type = ENV_TYPES.get(dotted_key, str)
                try:
                    return _cast_env_value(env_val, target_type)
                except (ValueError, TypeError):
                    logger.warning("Invalid env value for %s=%s", env_var, env_val)

        # 3. YAML config
        yaml_val = _nested_get(self._file_config, dotted_key)
        if yaml_val is not None:
            return yaml_val

        # 4. Defaults
        default_val = _nested_get(DEFAULTS, dotted_key)
        return default_val if default_val is not None else default

    def reload(self, config_file: Path | None = None) -> None:
        """Reload configuration from disk."""
        self._load_env_files()
        self._file_config = self._load_yaml_chain(config_file)

    # =========================================================================
    # Repository settings
    # =========================================================================

    @property
    def repos(self) -> list[dict[str, Any]]:
        """Repository list from config."""
        if repos := self._file_config.get("repos"):
            return repos
        if repo := self._file_config.get("repo"):
            if isinstance(repo, str):
                return [{"path": repo}]
            return [repo]
        # Check CLI
        if "repos" in self._cli:
            return self._cli["repos"]
        return []

    # =========================================================================
    # LLM settings
    # =========================================================================

    @property
    def llm_provider(self) -> str:
        return self._get("llm.provider")

    @property
    def llm_model(self) -> str:
        return self._get("llm.model")

    @property
    def llm_temperature(self) -> float:
        return float(self._get("llm.temperature"))

    @property
    def llm_max_tokens(self) -> int:
        return int(self._get("llm.max_tokens"))

    @property
    def llm_num_retries(self) -> int:
        return int(self._get("llm.num_retries", 3))

    @property
    def llm_max_concurrent(self) -> int:
        return int(self._get("llm.max_concurrent"))

    @property
    def llm_max_calls(self) -> int:
        return int(self._get("llm.max_calls"))

    # =========================================================================
    # Extraction settings
    # =========================================================================

    @property
    def merge_strategy(self) -> str:
        return self._get("extraction.merge_strategy")

    @property
    def min_diff_lines(self) -> int:
        return int(self._get("extraction.min_diff_lines"))

    @property
    def max_diff_lines(self) -> int:
        return int(self._get("extraction.max_diff_lines"))

    @property
    def include_file_contents(self) -> bool:
        return bool(self._get("extraction.include_file_contents"))

    @property
    def max_file_size_kb(self) -> int:
        return int(self._get("extraction.max_file_size_kb"))

    @property
    def extraction_since(self) -> str | None:
        return self._get("extraction.since")

    @property
    def extraction_until(self) -> str | None:
        return self._get("extraction.until")

    # =========================================================================
    # Filtering settings
    # =========================================================================

    @property
    def exclude_authors(self) -> list[str]:
        return self._get("filtering.exclude_authors")

    @property
    def exclude_paths(self) -> list[str]:
        return self._get("filtering.exclude_paths")

    @property
    def exclude_extensions(self) -> list[str]:
        return self._get("filtering.exclude_extensions")

    @property
    def min_commit_message_length(self) -> int:
        return int(self._get("filtering.min_commit_message_length"))

    @property
    def remove_secrets(self) -> bool:
        return bool(self._get("filtering.remove_secrets"))

    @property
    def dedup_enabled(self) -> bool:
        return bool(self._get("filtering.dedup"))

    # =========================================================================
    # Enrichment settings
    # =========================================================================

    @property
    def generate_descriptions(self) -> bool:
        return bool(self._get("enrichment.generate_descriptions"))

    @property
    def description_quality_threshold(self) -> float:
        return float(self._get("enrichment.description_quality_threshold"))

    @property
    def classify_type(self) -> bool:
        return bool(self._get("enrichment.classify_type"))

    @property
    def classify_difficulty(self) -> bool:
        return bool(self._get("enrichment.classify_difficulty"))

    @property
    def skip_if_enriched(self) -> bool:
        return bool(self._get("enrichment.skip_if_enriched"))

    # =========================================================================
    # Output settings
    # =========================================================================

    @property
    def output_dir(self) -> Path:
        return Path(self._get("output.dir")).expanduser()

    @property
    def output_mode(self) -> str:
        return self._get("output.mode")

    @property
    def output_formats(self) -> list[str]:
        return self._get("output.formats")

    @property
    def max_context_tokens(self) -> int:
        return int(self._get("output.max_context_tokens"))

    @property
    def include_repo_tree(self) -> bool:
        return bool(self._get("output.include_repo_tree"))

    # =========================================================================
    # Logging settings
    # =========================================================================

    @property
    def log_level(self) -> str:
        return self._get("logging.level")

    @property
    def log_progress(self) -> bool:
        return bool(self._get("logging.progress"))

    @property
    def log_verbose(self) -> bool:
        return bool(self._get("logging.verbose"))

    @property
    def log_file(self) -> str | None:
        return self._get("logging.file")


def init_config_dir() -> Path:
    """Create the global config directory and default files if they don't exist.

    Returns:
        Path to the global config directory.
    """
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not GLOBAL_CONFIG_FILE.exists():
        GLOBAL_CONFIG_FILE.write_text(
            yaml.dump(DEFAULTS, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    if not GLOBAL_ENV_FILE.exists():
        GLOBAL_ENV_FILE.write_text(
            "# code-dataset secrets\n"
            "# ANTHROPIC_API_KEY=sk-ant-api-...\n"
            "# OPENAI_API_KEY=sk-...\n"
            "# GOOGLE_API_KEY=AIza...\n",
            encoding="utf-8",
        )
    return GLOBAL_CONFIG_DIR
