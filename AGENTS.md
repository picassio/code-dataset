# AGENTS.md

## Project Overview

**code-dataset** extracts structured training datasets (SFT, DPO, RL) from local git repository history (merges, PRs, squash commits). It uses DSPy for structured LLM output and ships its own OAuth + LM system adapted from rlm-dspy — no rlm-dspy dependency, no LiteLLM.

## Setup Commands

```bash
# Install dependencies (uses uv, not pip)
uv sync

# Install with dev dependencies
uv sync --group dev

# Run CLI
uv run code-dataset --help

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Project Structure

```
src/code_dataset/
├── cli.py                    # Typer CLI entry point
├── config.py                 # Config: yaml + .env + defaults, precedence chain
├── oauth/                    # OAuth system (adapted from rlm-dspy)
│   ├── base.py              # OAuthProvider ABC, credentials, PKCE, callback server
│   ├── anthropic.py         # Anthropic OAuth (Claude Pro/Max)
│   ├── google.py            # Google OAuth (Gemini via Cloud Code Assist)
│   └── manager.py           # Provider registry, auto-refresh
├── lm/                       # LM classes (adapted from rlm-dspy, NOT litellm)
│   ├── factory.py           # create_lm(config) → dspy.LM
│   ├── anthropic_lm.py     # AnthropicOAuthLM (extends dspy BaseLM)
│   ├── anthropic_types.py  # Claude Code types, tool mapping
│   ├── google_lm.py        # GoogleOAuthLM (extends dspy BaseLM)
│   └── models.py           # Model registry (context windows, pricing)
├── extraction/               # Git data extraction
│   ├── git_extractor.py     # Core: extract merges/squashes from git
│   ├── merge_detector.py    # Detect merge commits
│   ├── squash_detector.py   # Detect squash merges (heuristics)
│   ├── diff_parser.py       # Parse unified diffs
│   └── context_builder.py   # Build file context around changes
├── filtering/                # Data quality filtering
│   ├── quality_filter.py    # Size, file type, message quality filters
│   ├── security_filter.py   # Secret/PII detection (regex + optional LLM)
│   ├── dedup.py             # Near-duplicate detection
│   └── heuristics.py        # Bot detection, trivial change detection
├── enrichment/               # LLM-based enrichment via DSPy
│   ├── signatures.py        # DSPy Signatures (MergeDescription, etc.)
│   ├── description_gen.py   # ChainOfThought(MergeDescription)
│   ├── classifier.py        # Predict(DiffClassifier)
│   └── quality_scorer.py    # Predict(DescriptionQuality)
├── formatting/               # Output dataset formatting
│   ├── sft_formatter.py     # SFT: instruction → patch
│   ├── dpo_formatter.py     # DPO: chosen vs rejected pairs
│   ├── rl_formatter.py      # RL: with test verification
│   └── context_window.py    # Smart context truncation
└── utils/
    ├── language_detect.py   # Programming language detection
    └── stats.py             # Dataset statistics & reporting
```

## Architecture & Key Patterns

### Configuration Precedence
```
CLI flags > env vars > ./config.yaml > ~/.code-dataset/config.yaml > defaults
```
- All settings in `config.yaml` (never secrets)
- Secrets in `.env` files only (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.)
- OAuth tokens auto-managed in `~/.code-dataset/oauth/credentials.json`
- Env var prefix: `CODE_DATASET_*`

### LLM Provider Pattern
- **NEVER use LiteLLM** — we have our own OAuth LM classes
- `lm/factory.py` → `create_lm(config)` returns a `dspy.LM`
- Anthropic: `AnthropicOAuthLM` (supports both `sk-ant-api-*` and `sk-ant-oat-*` OAuth tokens)
- Google: `GoogleOAuthLM` (via Cloud Code Assist API, custom headers)
- OpenAI: `dspy.LM("openai/model")` directly
- OAuth code adapted from `rlm-dspy/src/rlm_dspy/core/oauth/` and `rlm-dspy/src/rlm_dspy/core/anthropic_oauth_lm.py`

### DSPy Signatures (Structured Output)
All LLM output is extracted via DSPy Signatures — typed fields, no free-form parsing:
- `MergeDescription` — reverse-engineer task description from diff
- `DescriptionQuality` — score existing commit messages (0.0–1.0)
- `DiffClassifier` — classify type (bugfix/feature/refactor) and difficulty
- `SecurityCheck` — detect secrets/PII in diffs
- Use `dspy.ChainOfThought()` for generation, `dspy.Predict()` for classification

### Pipeline Stages
1. **Extract** — git merge/squash detection → raw_merges.jsonl
2. **Filter** — bots, trivial, secrets, dedup → filtered_merges.jsonl
3. **Enrich** — DSPy LLM description generation → enriched_merges.jsonl
4. **Format** — SFT/DPO/RL output datasets

## Code Style

- Python 3.12+
- Ruff for linting and formatting (`line-length = 120`)
- Type hints everywhere (use `from __future__ import annotations`)
- Docstrings: Google style
- Imports: sorted by ruff (`isort` rules via `select = ["I"]`)
- Use `pathlib.Path` not `os.path`
- Use `dataclass` or `pydantic.BaseModel` for data structures
- Use `logging` module, not `print()` for operational output
- Use `rich` for CLI user-facing output

## Testing

```bash
uv run pytest                    # Run all tests
uv run pytest tests/test_config.py  # Run specific test file
uv run pytest -v                 # Verbose output
uv run pytest -x                 # Stop on first failure
```

- Tests in `tests/` directory
- Use `pytest` fixtures for git repo setup
- No integration tests that call real LLM APIs in default test run
- Use `unittest.mock` to mock LLM calls in enrichment tests
- Test fixture git repos created in `tests/fixtures/` via `git init` in setup

## Git & PR Guidelines

- Branch naming: `feature/`, `bugfix/`, `refactor/`, `docs/`
- Commit messages: imperative mood, descriptive (this project literally trains on good commit messages)
- Run `uv run ruff check src/ tests/` and `uv run pytest` before committing
- Keep files under 500 lines; split if larger

## Security Considerations

- Never commit `.env` files or OAuth credentials
- `config.yaml` must never contain API keys or tokens
- `security_filter.py` detects secrets in extracted diffs before they enter the dataset
- OAuth credentials stored in `~/.code-dataset/oauth/credentials.json` with `0o600` permissions
- Regex patterns for common secret formats (sk-*, AIza*, gsk_*, etc.)

## Key Files Reference

| Need to... | Look at |
|-----------|---------|
| Understand the full plan | `PLAN.md` |
| Add a new LLM provider | `src/code_dataset/lm/factory.py` |
| Add a new DSPy signature | `src/code_dataset/enrichment/signatures.py` |
| Change config defaults | `src/code_dataset/config.py` → `DEFAULTS` dict |
| Add a CLI command | `src/code_dataset/cli.py` |
| Add a filter | `src/code_dataset/filtering/` |
| Understand OAuth flow | `src/code_dataset/oauth/base.py` |
| See rlm-dspy source (reference) | `/home/ubuntu/projects/rlm-dspy/src/rlm_dspy/` |
