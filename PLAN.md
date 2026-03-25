# Code Dataset Extraction Pipeline — Plan

## Goal
Build a tool that extracts structured training data (SFT, DPO/preference, RL) from **local private git repositories**, where we only have the git history — no GitHub API, no issue tracker, minimal PR descriptions. Uses **DSPy** for structured LLM output extraction. Ships its own OAuth + LM code (adapted from rlm-dspy) — **no rlm-dspy dependency, no LiteLLM**.

---

## 1. Related Work & Research

### Key Papers

| Paper | Year | Relevance |
|-------|------|-----------|
| **OctoPack / CommitPack** ([arXiv:2308.07124](https://arxiv.org/abs/2308.07124)) | 2023 | 4TB of git commits as instruction tuning data. `old_contents → new_contents + commit_message`. Achieved 46.2% HumanEval. **Our closest ancestor.** |
| **CommitPackFT** | 2023 | Filtering for instruction-like commit messages is crucial. Key filters: length, imperative mood, no "wip/fix/update" noise. |
| **StarCoder 2 / The Stack v2** ([arXiv:2402.19173](https://arxiv.org/abs/2402.19173)) | 2024 | Includes GitHub **pull requests** as training data. Validates PRs as valuable signal. |
| **SWE-bench** ([arXiv:2310.06770](https://arxiv.org/abs/2310.06770)) | 2023 | Issue description + codebase → patch format. Template for our SFT output. |
| **Multi-SWE-RL** ([arXiv:2504.02605](https://arxiv.org/abs/2504.02605)) | 2025 | 4,723 RL instances across 7 languages. Open-sourced pipeline. **Directly relevant to our RL format.** |
| **DeepSeek-R1** ([arXiv:2501.12948](https://arxiv.org/abs/2501.12948)) | 2025 | Pure RL (GRPO) with test-pass as verifiable reward. **Validates our CI-as-reward idea.** |
| **Self-Instruct** ([arXiv:2212.10560](https://arxiv.org/abs/2212.10560)) | 2022 | Generating synthetic instructions from LLM. **Foundation for our synthetic description generation from diffs.** |
| **WizardCoder / Evol-Instruct** ([arXiv:2306.08568](https://arxiv.org/abs/2306.08568)) | 2023 | Evolves simple code instructions into complex ones. |
| **SWEET-RL** ([arXiv:2503.15478](https://arxiv.org/abs/2503.15478)) | 2025 | Multi-turn RL with step-wise credit assignment. Relevant for PR-as-multi-turn. |
| **Long Code Arena** ([arXiv:2406.11612](https://arxiv.org/abs/2406.11612)) | 2024 | Benchmarks for commit message generation from diffs. |

---

## 2. Decisions

| Decision | Choice |
|----------|--------|
| LLM API usage | ✅ Yes — send diffs to LLM APIs for synthetic generation |
| Granularity | PR/merge-level only |
| LLM providers | Multiple — own OAuth (adapted from rlm-dspy) |
| Multiple repos | User chooses: `--combine` or `--separate` |
| Merge strategies | Handle both merge commits AND squash merges |
| LLM framework | **Never LiteLLM** — own OAuth LMs (copied from rlm-dspy) |
| Structured output | DSPy signatures |
| Config | `config.yaml` (all settings) + `.env` (secrets only) |
| Dependency | **Self-contained** — copy needed code from rlm-dspy, no pip dependency |

---

## 3. Files to Copy from rlm-dspy

We copy and adapt these files from `/home/ubuntu/projects/rlm-dspy/src/rlm_dspy/`. No rlm-dspy pip dependency.

### 3.1 OAuth System (copy as-is, adapt paths)

| rlm-dspy source | Our destination | What to change |
|-----------------|-----------------|----------------|
| `core/oauth/__init__.py` | `src/code_dataset/oauth/__init__.py` | Change `~/.rlm/oauth/` → `~/.code-dataset/oauth/` |
| `core/oauth/base.py` | `src/code_dataset/oauth/base.py` | Change `OAUTH_DIR` path |
| `core/oauth/anthropic.py` | `src/code_dataset/oauth/anthropic.py` | As-is |
| `core/oauth/google.py` | `src/code_dataset/oauth/google.py` | As-is |
| `core/oauth/manager.py` | `src/code_dataset/oauth/manager.py` | Fix imports |

### 3.2 LM Classes (copy as-is, adapt imports)

| rlm-dspy source | Our destination | What to change |
|-----------------|-----------------|----------------|
| `core/anthropic_oauth_lm.py` | `src/code_dataset/lm/anthropic_lm.py` | Fix imports to our oauth package |
| `core/anthropic_types.py` | `src/code_dataset/lm/anthropic_types.py` | As-is |
| `core/google_oauth_lm.py` | `src/code_dataset/lm/google_lm.py` | Fix imports |
| `core/models.py` | `src/code_dataset/lm/models.py` | Only keep Anthropic + Google + OpenAI models |

### 3.3 What NOT to copy
- `rlm.py`, `builder.py`, `daemon.py` — RLM-specific logic
- `vector_index.py`, `embeddings.py`, `ast_index.py` — search/indexing
- `gepa_optimizer.py`, `simba_optimizer.py` — optimization
- `trace_collector.py`, `callbacks.py` — tracing
- All CLI files except auth patterns

---

## 4. Configuration Architecture

### 4.1 File Layout

```
~/.code-dataset/                    # Global config dir
├── config.yaml                     # All settings (no secrets here)
├── .env                            # Secrets: API keys, tokens
└── oauth/
    └── credentials.json            # OAuth tokens (auto-managed)

./config.yaml                       # Project-level override (optional)
                                    # Takes precedence over ~/.code-dataset/config.yaml
```

### 4.2 Precedence (highest → lowest)

```
1. CLI flags              (--model, --provider, --output-dir)
2. Environment variables  (CODE_DATASET_MODEL, ANTHROPIC_API_KEY)
3. Project config.yaml    (./config.yaml in current dir)
4. Global config.yaml     (~/.code-dataset/config.yaml)
5. Built-in defaults
```

### 4.3 config.yaml — Full Specification

```yaml
# =============================================================================
# Code Dataset Configuration
# =============================================================================
# All settings are configurable here. Secrets go in .env file.
# Priority: CLI flags > env vars > ./config.yaml > ~/.code-dataset/config.yaml > defaults

# =============================================================================
# Repositories
# =============================================================================
repos:
  - path: /path/to/repo1
    name: my-backend                # optional, defaults to folder name
    main_branch: main               # optional, defaults to "main"
  - path: /path/to/repo2
    name: my-frontend
    main_branch: master

# Single repo shorthand (alternative to repos list):
# repo: /path/to/repo

# =============================================================================
# LLM Provider Settings
# =============================================================================
llm:
  # Provider: anthropic | google | openai
  provider: anthropic

  # Model ID (provider-specific)
  model: claude-sonnet-4-20250514

  # Temperature for generation (0.0 = deterministic)
  temperature: 0.3

  # Max tokens per response
  max_tokens: 4096

  # Retry count on transient errors
  num_retries: 3

  # Concurrency: how many LLM calls in parallel
  max_concurrent: 5

  # Cost control: max total LLM calls per run
  max_calls: 500

# =============================================================================
# Git Extraction
# =============================================================================
extraction:
  # Merge detection strategy
  # auto: detect both merge commits and squash merges
  # merge_commit: only extract merge commits
  # squash: only extract squash merges
  # all: extract everything (merge + squash + large single commits)
  merge_strategy: auto

  # Diff size limits (lines)
  min_diff_lines: 5
  max_diff_lines: 5000

  # Include full file contents (before/after), not just diffs
  include_file_contents: true

  # Max individual file size to include (KB)
  max_file_size_kb: 100

  # Date range filter (optional)
  # since: "2024-01-01"
  # until: "2025-01-01"

# =============================================================================
# Filtering
# =============================================================================
filtering:
  # Authors to exclude (bots, CI)
  exclude_authors:
    - "dependabot[bot]"
    - "renovate[bot]"
    - "github-actions[bot]"
    - "semantic-release-bot"

  # File path patterns to exclude (gitignore-style)
  exclude_paths:
    - "*.lock"
    - "package-lock.json"
    - "yarn.lock"
    - "pnpm-lock.yaml"
    - "Pipfile.lock"
    - "poetry.lock"
    - "*.min.js"
    - "*.min.css"
    - "vendor/"
    - "node_modules/"
    - "dist/"
    - ".git/"

  # File extensions to exclude (binary, assets)
  exclude_extensions:
    - ".svg"
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".gif"
    - ".ico"
    - ".woff"
    - ".woff2"
    - ".ttf"
    - ".eot"
    - ".mp3"
    - ".mp4"
    - ".pdf"
    - ".zip"
    - ".tar"
    - ".gz"

  # Minimum commit message length to consider
  min_commit_message_length: 10

  # Enable secret/PII detection and redaction
  remove_secrets: true

  # Enable near-duplicate detection
  dedup: true

# =============================================================================
# Enrichment (LLM-based)
# =============================================================================
enrichment:
  # Generate synthetic descriptions for poor/missing ones
  generate_descriptions: true

  # Quality threshold: descriptions below this score get regenerated
  # 0.0 = regenerate everything, 1.0 = never regenerate
  description_quality_threshold: 0.5

  # Classify change type (bugfix, feature, refactor, etc.)
  classify_type: true

  # Classify difficulty (easy, medium, hard)
  classify_difficulty: true

  # Skip items that were already enriched (for incremental runs)
  skip_if_enriched: true

# =============================================================================
# Output
# =============================================================================
output:
  # Output directory
  dir: ./output

  # Multi-repo handling: "separate" (one dataset per repo) or "combine" (merged)
  mode: separate

  # Which dataset formats to generate
  formats:
    - sft     # Supervised Fine-Tuning (instruction → patch)
    - dpo     # Direct Preference Optimization (chosen vs rejected)
    - rl      # Reinforcement Learning (with test verification)

  # Max context window size (tokens) for file contents
  max_context_tokens: 8192

  # Include repo structure tree in context
  include_repo_tree: true

# =============================================================================
# Logging
# =============================================================================
logging:
  # Log level: DEBUG, INFO, WARNING, ERROR
  level: INFO

  # Log file (optional, in addition to console)
  # file: ./code-dataset.log

  # Show progress bars
  progress: true

  # Verbose mode (show LLM calls, diffs being processed)
  verbose: false
```

### 4.4 .env — Secrets Only

```bash
# =============================================================================
# Code Dataset - Secrets
# =============================================================================
# Place this file at: ~/.code-dataset/.env  OR  ./.env (project-level)
# These are loaded automatically. NEVER commit this file.

# --- API Keys (used when not using OAuth) ---
ANTHROPIC_API_KEY=sk-ant-api-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...

# --- OAuth tokens (usually auto-managed, but can be set manually) ---
# ANTHROPIC_OAUTH_TOKEN=sk-ant-oat-...

# --- Optional overrides ---
# CODE_DATASET_MODEL=claude-sonnet-4-20250514
# CODE_DATASET_PROVIDER=anthropic
```

### 4.5 Environment Variable Mappings

| Config key | Env var | Type |
|-----------|---------|------|
| `llm.provider` | `CODE_DATASET_PROVIDER` | str |
| `llm.model` | `CODE_DATASET_MODEL` | str |
| `llm.max_calls` | `CODE_DATASET_MAX_CALLS` | int |
| `llm.max_concurrent` | `CODE_DATASET_MAX_CONCURRENT` | int |
| `output.dir` | `CODE_DATASET_OUTPUT_DIR` | str |
| `output.mode` | `CODE_DATASET_OUTPUT_MODE` | str |
| `logging.level` | `CODE_DATASET_LOG_LEVEL` | str |
| `logging.verbose` | `CODE_DATASET_VERBOSE` | bool |
| *(API keys)* | `ANTHROPIC_API_KEY` | str |
| *(API keys)* | `ANTHROPIC_OAUTH_TOKEN` | str |
| *(API keys)* | `OPENAI_API_KEY` | str |
| *(API keys)* | `GOOGLE_API_KEY` | str |

---

## 5. DSPy Signatures for Structured Extraction

### 5.1 MergeDescription — Reverse-engineer task from diff

```python
class MergeDescription(dspy.Signature):
    """Analyze a code diff and reverse-engineer the task/issue that produced it.
    Write the description as a clear developer task/ticket."""

    diff: str = dspy.InputField(desc="Unified diff of all code changes")
    branch_name: str = dspy.InputField(desc="Git branch name if available, else empty")
    commit_messages: str = dspy.InputField(desc="All commit messages on the branch, newline-separated")
    file_list: str = dspy.InputField(desc="List of changed files, newline-separated")

    title: str = dspy.OutputField(desc="One-line task title")
    description: str = dspy.OutputField(desc="2-5 sentence task description explaining what and why")
    change_type: str = dspy.OutputField(desc="One of: bugfix, feature, refactor, test, docs, chore")
    difficulty: str = dspy.OutputField(desc="One of: easy, medium, hard")
    languages: list[str] = dspy.OutputField(desc="Programming languages involved")
```

### 5.2 DescriptionQuality — Score existing descriptions

```python
class DescriptionQuality(dspy.Signature):
    """Evaluate whether a commit/merge description is good enough to use
    as training data instruction, or needs synthetic regeneration."""

    description: str = dspy.InputField(desc="The commit/PR description to evaluate")
    diff_summary: str = dspy.InputField(desc="Summary of the code diff (files changed, stats)")

    quality_score: float = dspy.OutputField(desc="Quality score from 0.0 (useless) to 1.0 (excellent)")
    is_instructive: bool = dspy.OutputField(desc="True if description could serve as a task instruction")
    reason: str = dspy.OutputField(desc="Brief explanation of the quality assessment")
```

### 5.3 DiffClassifier — Lightweight classification

```python
class DiffClassifier(dspy.Signature):
    """Classify a code diff by change type and difficulty."""

    diff: str = dspy.InputField(desc="Unified diff")
    file_list: str = dspy.InputField(desc="Files changed, newline-separated")

    change_type: str = dspy.OutputField(desc="One of: bugfix, feature, refactor, test, docs, chore")
    difficulty: str = dspy.OutputField(desc="One of: easy, medium, hard")
    summary: str = dspy.OutputField(desc="One-line summary of the change")
```

### 5.4 SecurityCheck — Detect secrets/PII in diffs

```python
class SecurityCheck(dspy.Signature):
    """Check a code diff for leaked secrets, API keys, PII, or sensitive data."""

    diff: str = dspy.InputField(desc="Code diff to check")

    has_secrets: bool = dspy.OutputField(desc="True if API keys, tokens, or passwords found")
    has_pii: bool = dspy.OutputField(desc="True if personal information found")
    findings: list[str] = dspy.OutputField(desc="Description of each finding")
    safe_to_use: bool = dspy.OutputField(desc="True if safe to include in training data")
```

### 5.5 How they're used

```python
import dspy
from code_dataset.lm.factory import create_lm

# Setup
lm = create_lm(config)  # Uses our copied OAuth LMs
dspy.configure(lm=lm)

# Generate description (ChainOfThought for better reasoning)
describe = dspy.ChainOfThought(MergeDescription)
result = describe(
    diff=merge.diff,
    branch_name=merge.branch_name,
    commit_messages="\n".join(merge.commit_messages),
    file_list="\n".join(merge.files_changed),
)
# result.title, result.description, result.change_type — all typed, no parsing

# Score quality (simple Predict, no chain-of-thought needed)
scorer = dspy.Predict(DescriptionQuality)
quality = scorer(
    description=merge.commit_message,
    diff_summary=f"{len(merge.files_changed)} files, +{merge.insertions}/-{merge.deletions}",
)
# quality.quality_score → float, quality.is_instructive → bool

# Security check (Predict)
checker = dspy.Predict(SecurityCheck)
security = checker(diff=merge.diff)
# security.safe_to_use → bool
```

---

## 6. LM Factory — Provider Creation

```python
# src/code_dataset/lm/factory.py

"""LM factory — creates DSPy LMs using our own OAuth system.

NEVER uses LiteLLM. Uses:
- AnthropicOAuthLM (copied from rlm-dspy) for Anthropic
- GoogleOAuthLM (copied from rlm-dspy) for Google
- dspy.LM for OpenAI (direct, no litellm)
"""

import os
import dspy
from ..config import Config

def create_lm(config: Config) -> dspy.LM:
    """Create a DSPy-compatible LM from config.

    Reads provider/model from config.yaml, secrets from .env.
    """
    provider = config.llm_provider    # from config.yaml
    model = config.llm_model          # from config.yaml
    temperature = config.llm_temperature
    max_tokens = config.llm_max_tokens
    num_retries = config.llm_num_retries

    if provider == "anthropic":
        from .anthropic_lm import AnthropicOAuthLM, get_anthropic_api_key
        api_key = get_anthropic_api_key()  # .env or OAuth credentials
        return AnthropicOAuthLM(
            model=model,
            auth_token=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            num_retries=num_retries,
        )

    elif provider == "google":
        from .google_lm import GoogleOAuthLM
        return GoogleOAuthLM(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            num_retries=num_retries,
        )

    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in .env or environment")
        return dspy.LM(
            f"openai/{model}",
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported: anthropic, google, openai"
        )
```

---

## 7. Config Implementation

```python
# src/code_dataset/config.py

"""Configuration management.

Precedence: CLI flags > env vars > ./config.yaml > ~/.code-dataset/config.yaml > defaults
Secrets loaded from: .env file (never stored in config.yaml)
"""

from pathlib import Path
import os
import yaml

GLOBAL_CONFIG_DIR = Path.home() / ".code-dataset"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.yaml"
GLOBAL_ENV_FILE = GLOBAL_CONFIG_DIR / ".env"
PROJECT_CONFIG_FILE = Path("./config.yaml")
PROJECT_ENV_FILE = Path("./.env")

DEFAULTS = {
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
    },
    "filtering": {
        "exclude_authors": ["dependabot[bot]", "renovate[bot]", "github-actions[bot]"],
        "exclude_paths": ["*.lock", "package-lock.json", "node_modules/", "vendor/"],
        "exclude_extensions": [".svg", ".png", ".jpg", ".gif", ".ico", ".woff"],
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
    },
}

ENV_MAPPINGS = {
    "llm.provider": "CODE_DATASET_PROVIDER",
    "llm.model": "CODE_DATASET_MODEL",
    "llm.max_calls": "CODE_DATASET_MAX_CALLS",
    "llm.max_concurrent": "CODE_DATASET_MAX_CONCURRENT",
    "output.dir": "CODE_DATASET_OUTPUT_DIR",
    "output.mode": "CODE_DATASET_OUTPUT_MODE",
    "logging.level": "CODE_DATASET_LOG_LEVEL",
    "logging.verbose": "CODE_DATASET_VERBOSE",
}

class Config:
    """Unified config with precedence: CLI > env > project yaml > global yaml > defaults."""

    def __init__(self, config_file: Path | None = None, cli_overrides: dict | None = None):
        self._load_env_files()
        self._file_config = self._load_yaml(config_file)
        self._cli = cli_overrides or {}

    def _load_env_files(self):
        """Load .env files (project-level first, then global)."""
        for env_path in [PROJECT_ENV_FILE, GLOBAL_ENV_FILE]:
            if env_path.exists():
                _load_dotenv(env_path)

    def _load_yaml(self, explicit: Path | None) -> dict:
        """Load and merge YAML configs."""
        config = {}
        # Global config
        if GLOBAL_CONFIG_FILE.exists():
            config = _deep_merge(config, _read_yaml(GLOBAL_CONFIG_FILE))
        # Project config
        if PROJECT_CONFIG_FILE.exists():
            config = _deep_merge(config, _read_yaml(PROJECT_CONFIG_FILE))
        # Explicit config
        if explicit and explicit.exists():
            config = _deep_merge(config, _read_yaml(explicit))
        return config

    def _get(self, dotted_key: str, default=None):
        """Get config value with full precedence chain."""
        # 1. CLI override
        if dotted_key in self._cli:
            return self._cli[dotted_key]
        # 2. Environment variable
        env_var = ENV_MAPPINGS.get(dotted_key)
        if env_var and (val := os.environ.get(env_var)):
            return _cast(val, default)
        # 3. YAML config (nested lookup)
        val = _nested_get(self._file_config, dotted_key)
        if val is not None:
            return val
        # 4. Defaults
        val = _nested_get(DEFAULTS, dotted_key)
        return val if val is not None else default

    # === Convenience properties ===

    @property
    def repos(self) -> list[dict]:
        """Repository list from config."""
        if repos := self._file_config.get("repos"):
            return repos
        if repo := self._file_config.get("repo"):
            if isinstance(repo, str):
                return [{"path": repo}]
            return [repo]
        return []

    @property
    def llm_provider(self) -> str:
        return self._get("llm.provider")
    @property
    def llm_model(self) -> str:
        return self._get("llm.model")
    @property
    def llm_temperature(self) -> float:
        return self._get("llm.temperature")
    @property
    def llm_max_tokens(self) -> int:
        return self._get("llm.max_tokens")
    @property
    def llm_num_retries(self) -> int:
        return self._get("llm.num_retries")
    @property
    def llm_max_concurrent(self) -> int:
        return self._get("llm.max_concurrent")
    @property
    def llm_max_calls(self) -> int:
        return self._get("llm.max_calls")

    @property
    def merge_strategy(self) -> str:
        return self._get("extraction.merge_strategy")
    @property
    def min_diff_lines(self) -> int:
        return self._get("extraction.min_diff_lines")
    @property
    def max_diff_lines(self) -> int:
        return self._get("extraction.max_diff_lines")

    @property
    def output_dir(self) -> str:
        return self._get("output.dir")
    @property
    def output_mode(self) -> str:
        return self._get("output.mode")
    @property
    def output_formats(self) -> list[str]:
        return self._get("output.formats")
    @property
    def max_context_tokens(self) -> int:
        return self._get("output.max_context_tokens")

    # ... (more properties for all config sections)
```

---

## 8. Module Structure

```
code-dataset/
├── PLAN.md
├── README.md
├── pyproject.toml
├── config.example.yaml              # Full annotated example
├── .env.example                     # Example secrets file
│
├── src/
│   └── code_dataset/
│       ├── __init__.py
│       ├── cli.py                   # Typer CLI entry point
│       │
│       ├── config.py                # Config management (yaml + env + defaults)
│       │
│       ├── oauth/                   # Copied from rlm-dspy, paths adapted
│       │   ├── __init__.py          # ← from rlm-dspy core/oauth/__init__.py
│       │   ├── base.py             # ← from rlm-dspy core/oauth/base.py
│       │   ├── anthropic.py        # ← from rlm-dspy core/oauth/anthropic.py
│       │   ├── google.py           # ← from rlm-dspy core/oauth/google.py
│       │   └── manager.py          # ← from rlm-dspy core/oauth/manager.py
│       │
│       ├── lm/                      # LM classes — copied from rlm-dspy
│       │   ├── __init__.py
│       │   ├── factory.py           # create_lm(config) → dspy.LM
│       │   ├── anthropic_lm.py     # ← from rlm-dspy core/anthropic_oauth_lm.py
│       │   ├── anthropic_types.py  # ← from rlm-dspy core/anthropic_types.py
│       │   ├── google_lm.py        # ← from rlm-dspy core/google_oauth_lm.py
│       │   └── models.py           # ← from rlm-dspy core/models.py (trimmed)
│       │
│       ├── extraction/
│       │   ├── __init__.py
│       │   ├── git_extractor.py     # Core: extract merges from git repo
│       │   ├── merge_detector.py    # Detect merge commits
│       │   ├── squash_detector.py   # Detect squash merges (heuristics)
│       │   ├── diff_parser.py       # Parse unified diffs
│       │   └── context_builder.py   # Build file context around changes
│       │
│       ├── filtering/
│       │   ├── __init__.py
│       │   ├── quality_filter.py    # Size, file type filters
│       │   ├── security_filter.py   # Regex + optional DSPy secret detection
│       │   ├── dedup.py             # Near-duplicate detection
│       │   └── heuristics.py        # Bot detection, trivial changes
│       │
│       ├── enrichment/
│       │   ├── __init__.py
│       │   ├── signatures.py        # All DSPy Signatures
│       │   ├── description_gen.py   # ChainOfThought(MergeDescription)
│       │   ├── classifier.py        # Predict(DiffClassifier)
│       │   └── quality_scorer.py    # Predict(DescriptionQuality)
│       │
│       ├── formatting/
│       │   ├── __init__.py
│       │   ├── sft_formatter.py     # SFT dataset format
│       │   ├── dpo_formatter.py     # DPO preference pairs
│       │   ├── rl_formatter.py      # RL format with test verification
│       │   └── context_window.py    # Smart context truncation
│       │
│       └── utils/
│           ├── __init__.py
│           ├── language_detect.py   # Programming language detection
│           └── stats.py             # Dataset statistics & reporting
│
├── tests/
│   ├── test_config.py
│   ├── test_git_extractor.py
│   ├── test_merge_detector.py
│   ├── test_filters.py
│   ├── test_enrichment.py
│   └── fixtures/                    # Sample git repos for testing
│
└── output/                          # Generated datasets (gitignored)
```

---

## 9. Package Manager: uv

We use **uv** (v0.9.26+) for fast dependency management. No pip, no venv manually.

```bash
# Initial setup
cd code-dataset
uv init                          # creates pyproject.toml if missing
uv sync                          # install all deps + create .venv
uv sync --group dev              # include dev dependencies

# Adding dependencies
uv add dspy anthropic httpx      # add to [project.dependencies]
uv add --group dev pytest ruff   # add to [project.optional-dependencies.dev]

# Running
uv run code-dataset --help       # run CLI through uv
uv run pytest                    # run tests

# Lock file
uv lock                          # generate/update uv.lock
```

### pyproject.toml

```toml
[project]
name = "code-dataset"
version = "0.1.0"
description = "Extract training datasets (SFT, DPO, RL) from git repository history"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }

dependencies = [
    # DSPy for structured LLM output (3.x with Signature, ChainOfThought, Predict)
    "dspy>=3.1.3",

    # Anthropic SDK (for OAuth LM — direct, not via litellm)
    "anthropic>=0.86.0",

    # HTTP client (for Google OAuth LM + general requests)
    "httpx>=0.28.1",

    # Git operations
    "gitpython>=3.1.46",

    # CLI
    "typer>=0.24.1",
    "rich>=14.3.3",

    # Config
    "pyyaml>=6.0.3",

    # Data validation
    "pydantic>=2.12.5",
]

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "ruff>=0.15.7",
]

[project.scripts]
code-dataset = "code_dataset.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/code_dataset"]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## 10. CLI Interface

```bash
# =============================================================================
# Authentication (uses our copied OAuth system)
# =============================================================================
code-dataset auth login anthropic     # OAuth login (opens browser)
code-dataset auth login google        # Google OAuth login
code-dataset auth status              # Show all provider status
code-dataset auth logout anthropic    # Remove credentials

# =============================================================================
# Config management
# =============================================================================
code-dataset config init              # Create ~/.code-dataset/config.yaml + .env
code-dataset config show              # Display current effective config
code-dataset config edit              # Open config in $EDITOR

# =============================================================================
# Full pipeline
# =============================================================================
code-dataset run                      # Run all stages using config.yaml
code-dataset run --config ./my.yaml   # Use specific config file
code-dataset run /path/to/repo        # Single repo, auto-config
code-dataset run /repo1 /repo2 --combine  # Multi-repo, combined output

# =============================================================================
# Stage by stage
# =============================================================================
code-dataset extract                  # Stage 1: git extraction → raw.jsonl
code-dataset filter                   # Stage 2: filtering → filtered.jsonl
code-dataset enrich                   # Stage 3: LLM enrichment → enriched.jsonl
code-dataset format                   # Stage 4: format → sft/dpo/rl datasets

# With explicit files:
code-dataset extract /path/to/repo --output raw.jsonl
code-dataset filter raw.jsonl --output filtered.jsonl
code-dataset enrich filtered.jsonl --output enriched.jsonl
code-dataset format enriched.jsonl --formats sft,dpo,rl --output-dir ./output

# =============================================================================
# Utilities
# =============================================================================
code-dataset stats /path/to/repo           # Show repo merge statistics
code-dataset stats output/sft_dataset.jsonl # Show dataset statistics
code-dataset preview /path/to/repo -n 5    # Preview extractions (dry run)
```

---

## 11. Phased Implementation

### Phase 1: Scaffolding + OAuth + Config + Git Extraction
- [ ] `uv init` + `pyproject.toml` with dependencies + `uv sync`
- [ ] `config.py` — YAML + .env + defaults + precedence
- [ ] `config.example.yaml` + `.env.example`
- [ ] Copy OAuth system from rlm-dspy (adapt paths to `~/.code-dataset/`)
- [ ] Copy LM classes from rlm-dspy (adapt imports)
- [ ] `lm/factory.py` — `create_lm(config)`
- [ ] `extraction/merge_detector.py` — detect merge commits
- [ ] `extraction/squash_detector.py` — detect squash merges
- [ ] `extraction/git_extractor.py` — extract diffs, files, metadata
- [ ] `extraction/diff_parser.py` — parse unified diffs
- [ ] `cli.py` — `auth`, `config`, `extract`, `preview` commands
- [ ] `tests/test_config.py`, `tests/test_git_extractor.py`
- **Deliverable**: Can auth with LLM providers, extract raw data from any git repo

### Phase 2: Filtering + DSPy Enrichment
- [ ] `filtering/heuristics.py` — bot detection, trivial changes
- [ ] `filtering/quality_filter.py` — size, file type, message quality
- [ ] `filtering/security_filter.py` — regex-based secret detection
- [ ] `enrichment/signatures.py` — all 4 DSPy signatures
- [ ] `enrichment/quality_scorer.py` — score descriptions
- [ ] `enrichment/description_gen.py` — generate synthetic descriptions
- [ ] `enrichment/classifier.py` — type & difficulty
- [ ] `cli.py` — `filter`, `enrich` commands
- **Deliverable**: Every merge has quality description + classification

### Phase 3: Formatting + Multi-Repo + Polish
- [ ] `formatting/sft_formatter.py`
- [ ] `formatting/dpo_formatter.py`
- [ ] `formatting/rl_formatter.py`
- [ ] `formatting/context_window.py`
- [ ] Multi-repo `--combine` / `--separate`
- [ ] `utils/stats.py` — statistics & reports
- [ ] `cli.py` — `format`, `run`, `stats` commands
- [ ] `filtering/dedup.py` — near-duplicate detection
- [ ] End-to-end tests
- **Deliverable**: Complete pipeline, ready-to-train datasets
