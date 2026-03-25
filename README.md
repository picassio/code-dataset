# code-dataset

Extract structured training datasets (SFT, DPO, RL) from local git repository history for fine-tuning or reinforcement learning of code LLMs.

Turns your private repos into high-quality training data — no GitHub API needed, just a local clone.

## How It Works

```
Git Repository ──→ Extract ──→ Filter ──→ Enrich ──→ Format
                    │              │          │          │
              merge commits   remove bots   LLM adds   SFT, DPO, RL
              squash merges   redact secrets  task      JSONL datasets
              diffs, files    dedup          descriptions
```

**The core idea**: Every merged PR or squash commit represents a complete, reviewed unit of work. We extract these, and when commit messages are poor (which they often are in private repos), we use an LLM to reverse-engineer a clear task description from the code diff — essentially doing [Self-Instruct](https://arxiv.org/abs/2212.10560) on code changes.

## Features

- **Merge detection**: Both merge commits and squash merges (heuristic detection via PR numbers, bullet points, message patterns)
- **Quality filtering**: Bot exclusion, trivial change detection, auto-generated file removal, whitespace-only diff detection
- **Secret redaction**: Regex-based detection of API keys (OpenAI, Anthropic, AWS, GitHub, Slack, etc.), passwords, PII — automatically redacted before output
- **Deduplication**: Content-fingerprint based near-duplicate removal (catches cherry-picks, back-merges)
- **LLM enrichment via DSPy**: Structured output extraction with typed fields — no free-form text parsing
  - `MergeDescription`: Reverse-engineer task descriptions from diffs
  - `DescriptionQuality`: Score existing commit messages (0.0–1.0)
  - `DiffClassifier`: Classify change type (bugfix/feature/refactor) and difficulty (easy/medium/hard)
- **Three output formats**: SFT (instruction→patch), DPO (preference pairs), RL (with test verification)
- **Multi-repo support**: Process multiple repositories, combine or keep separate
- **OAuth authentication**: Anthropic Claude (Pro/Max), Google Gemini — no LiteLLM dependency
- **Self-contained**: Ships its own OAuth + LM system (adapted from [rlm-dspy](https://github.com/picassio/rlm-dspy))

## Quick Start

```bash
# Clone and install
git clone <repo-url> code-dataset
cd code-dataset
uv sync

# Authenticate with an LLM provider (for enrichment stage)
uv run code-dataset auth login anthropic

# Run the full pipeline on a repo
uv run code-dataset run /path/to/your/repo --branch main

# Or run stages individually
uv run code-dataset extract /path/to/repo -o raw.jsonl
uv run code-dataset filter raw.jsonl -o filtered.jsonl
uv run code-dataset enrich filtered.jsonl -o enriched.jsonl
uv run code-dataset format enriched.jsonl -d ./output
```

## Real-World Example

Tested on the [rlm-dspy](https://github.com/picassio/rlm-dspy) repository (a Python project with ~240 commits):

### Stage 1: Extract

```bash
$ uv run code-dataset extract /path/to/rlm-dspy --branch main

Extracting from /path/to/rlm-dspy...
  Found 0 merge commits (repo uses squash merges)
  Found 241 likely squash merges
  Extracted 234 records (7 skipped: diff too small)

✓ Wrote 234 records to raw_merges.jsonl
```

### Stage 2: Filter

```bash
$ uv run code-dataset filter raw_merges.jsonl

Loaded 234 records
  Redacting 2 secrets found in diffs
  Kept 234/234 records after filtering

✓ Kept 234/234 records → filtered_merges.jsonl
```

The security filter automatically detected and redacted 2 leaked API keys in the diff history.

### Stage 3: Enrich (LLM calls via Claude Sonnet 4)

```bash
$ uv run code-dataset enrich filtered_merges.jsonl

Using LLM: anthropic/claude-sonnet-4-20250514
  Scoring description quality...
  179 have good descriptions (score ≥ 0.5), 0 need enrichment
  Classifying change types and difficulty...
  Classified 10 records

✓ Enriched 179 records → enriched_merges.jsonl
```

Sample enriched record:

```
ID:          rlm-dspy/4fccc376f070
Title:       Add model refresh functionality and provider authentication detection to CLI
Score:       0.90 (original description was good enough)
Type:        feature
Difficulty:  medium
Languages:   [python]
Files:       3 changed, +376/-7
```

### Stage 4: Format

```bash
$ uv run code-dataset format enriched_merges.jsonl -d ./output

  SFT: 179 records
  DPO: 0 pairs
  RL:  29 records (with tests)

Total records: 179
By change type: feature=2, refactor=4, bugfix=3, docs=1
By difficulty: medium=6, easy=4
Languages: python, markdown, toml
Diff lines: min=41, avg=325.6, max=2430
Records with tests: 31 (17.3%)
Total changes: +35,776/-9,818 across 490 files

✓ Datasets written to ./output/
```

## Output Formats

### SFT (Supervised Fine-Tuning)

Each record maps a task description to the code changes that implement it:

```json
{
  "id": "my-project/abc123def456",
  "instruction": "Add retry logic to the HTTP client with exponential backoff\n\nImplement automatic retries for transient HTTP errors (5xx, timeouts) with configurable backoff.",
  "context": {
    "files_before": {
      "src/http_client.py": "import requests\n\nclass HttpClient:\n    ...",
      "src/config.py": "DEFAULT_TIMEOUT = 30\n..."
    },
    "repo_structure": "src/\n  http_client.py\n  config.py\ntests/\n  test_http.py"
  },
  "response": {
    "diff": "--- a/src/http_client.py\n+++ b/src/http_client.py\n@@ -1,5 +1,8 @@\n...",
    "files_after": {
      "src/http_client.py": "import requests\nfrom tenacity import retry...",
      "src/config.py": "DEFAULT_TIMEOUT = 30\nMAX_RETRIES = 3\n..."
    }
  },
  "metadata": {
    "repo_name": "my-project",
    "merge_type": "squash",
    "change_type": "feature",
    "difficulty": "medium",
    "languages": ["python"],
    "description_source": "synthetic",
    "quality_score": 0.85,
    "has_tests": true,
    "insertions": 87,
    "deletions": 12
  }
}
```

### DPO (Direct Preference Optimization)

Preference pairs from branch revision history — early incomplete commits (rejected) vs final merged state (chosen):

```json
{
  "id": "my-project/abc123def456/revision",
  "prompt": "Add retry logic to the HTTP client with exponential backoff",
  "chosen": "<final merged diff>",
  "rejected_context": {
    "early_commit_messages": ["wip: add retry", "fix: timeout issue"],
    "note": "Early branch state — incomplete implementation before review"
  },
  "chosen_context": {
    "final_commit_messages": ["add backoff config", "add tests for retry"],
    "note": "Final merged state — complete, reviewed implementation"
  },
  "metadata": {
    "pair_source": "revision_history",
    "num_commits": 6,
    "change_type": "feature",
    "difficulty": "medium"
  }
}
```

### RL (Reinforcement Learning)

Records where test files were modified — tests serve as the verifiable reward signal for GRPO/PPO training:

```json
{
  "id": "my-project/abc123def456/rl",
  "prompt": "Add retry logic to the HTTP client with exponential backoff",
  "test_files": {
    "tests/test_http.py": "import pytest\nfrom src.http_client import HttpClient\n\ndef test_retry_on_500():\n    ..."
  },
  "codebase_snapshot": {
    "src/http_client.py": "<file content before changes>",
    "src/config.py": "<file content before changes>"
  },
  "test_command": "pytest",
  "gold_patch": "<the actual merged diff>",
  "metadata": {
    "num_test_files": 1,
    "num_impl_files": 2,
    "change_type": "feature",
    "difficulty": "medium",
    "languages": ["python"]
  }
}
```

## Configuration

### config.yaml

All settings in one file. Copy `config.example.yaml` to get started:

```yaml
# Repositories to process
repos:
  - path: /path/to/repo1
    name: my-backend
    main_branch: main
  - path: /path/to/repo2
    name: my-frontend
    main_branch: master

# LLM for enrichment
llm:
  provider: anthropic        # anthropic | google | openai
  model: claude-sonnet-4-20250514
  temperature: 0.3
  max_calls: 500              # cost control

# Extraction
extraction:
  merge_strategy: auto        # auto | merge_commit | squash | all
  min_diff_lines: 5
  max_diff_lines: 5000

# Filtering
filtering:
  exclude_authors: ["dependabot[bot]", "renovate[bot]"]
  exclude_paths: ["*.lock", "node_modules/", "vendor/"]
  remove_secrets: true
  dedup: true

# Output
output:
  dir: ./output
  mode: separate              # separate (per-repo) | combine
  formats: [sft, dpo, rl]
  max_context_tokens: 8192
```

### .env (secrets only)

```bash
# API keys (if not using OAuth)
ANTHROPIC_API_KEY=sk-ant-api-...
OPENAI_API_KEY=sk-...
```

### Precedence

```
CLI flags > env vars (CODE_DATASET_*) > ./config.yaml > ~/.code-dataset/config.yaml > defaults
```

## CLI Reference

```bash
# Full pipeline
code-dataset run /repo1 /repo2 --combine     # Multi-repo, combined output
code-dataset run --config my.yaml             # Use custom config

# Individual stages
code-dataset extract /path/to/repo -o raw.jsonl
code-dataset filter raw.jsonl -o filtered.jsonl
code-dataset enrich filtered.jsonl -o enriched.jsonl
code-dataset format enriched.jsonl -d ./output --formats sft,dpo,rl

# Authentication
code-dataset auth login anthropic             # OAuth (opens browser)
code-dataset auth login google                # Google Gemini OAuth
code-dataset auth status                      # Show all providers

# Utilities
code-dataset preview /path/to/repo -n 5      # Dry run preview
code-dataset stats /path/to/repo              # Repo statistics
code-dataset stats output/sft_dataset.jsonl   # Dataset statistics
code-dataset config init                      # Create default config
code-dataset config show                      # Display effective config
```

## Architecture

```
src/code_dataset/
├── cli.py                     # Typer CLI (9 commands)
├── config.py                  # YAML + .env + defaults with precedence chain
│
├── oauth/                     # OAuth system (adapted from rlm-dspy)
│   ├── base.py               # OAuthProvider ABC, PKCE, callback server
│   ├── anthropic.py          # Claude Pro/Max OAuth
│   ├── google.py             # Gemini CLI + Antigravity OAuth
│   └── manager.py            # Provider registry, auto-refresh
│
├── lm/                        # LLM classes (NO LiteLLM)
│   ├── factory.py            # create_lm(config) → dspy.LM
│   ├── anthropic_lm.py       # AnthropicOAuthLM (streaming, OAuth + API key)
│   ├── google_lm.py          # GoogleOAuthLM (Cloud Code Assist API)
│   └── models.py             # Model registry (context windows, pricing)
│
├── extraction/                # Git data extraction
│   ├── git_extractor.py      # Core: extract merges from repo
│   ├── merge_detector.py     # Detect merge commits, parse branch names
│   ├── squash_detector.py    # Heuristic squash merge detection
│   ├── diff_parser.py        # Parse diffs, compute per-file stats
│   ├── context_builder.py    # Build repo tree snapshots
│   └── models.py             # MergeRecord, FileChange, CommitInfo
│
├── filtering/                 # Data quality filtering
│   ├── quality_filter.py     # Size, file type, message quality
│   ├── security_filter.py    # Secret/PII detection and redaction
│   ├── heuristics.py         # Bot, trivial change, autogen detection
│   └── dedup.py              # Content-fingerprint deduplication
│
├── enrichment/                # LLM enrichment via DSPy
│   ├── signatures.py         # DSPy Signatures (structured output schemas)
│   ├── description_gen.py    # Synthetic description generation
│   ├── quality_scorer.py     # Score existing descriptions
│   └── classifier.py         # Type and difficulty classification
│
├── formatting/                # Output dataset formatting
│   ├── sft_formatter.py      # SFT: instruction → patch
│   ├── dpo_formatter.py      # DPO: chosen vs rejected pairs
│   ├── rl_formatter.py       # RL: with test file extraction
│   └── context_window.py     # Token-budget context selection
│
└── utils/
    ├── language_detect.py    # File extension → language mapping
    └── stats.py              # Dataset statistics and reporting
```

## How Enrichment Works

When commit messages are poor (e.g., "fix", "wip", "update"), the enrichment stage uses an LLM to generate a proper task description:

1. **Score existing descriptions** — `DescriptionQuality` signature evaluates each commit message on a 0.0–1.0 scale
2. **Generate synthetic descriptions** — For messages below the threshold, `ChainOfThought(MergeDescription)` analyzes the diff and reverse-engineers what task would produce those changes
3. **Classify** — `DiffClassifier` determines change type and difficulty
4. **Detect languages** — File extensions are used (no LLM needed)

All LLM outputs use [DSPy Signatures](https://dspy.ai/) for guaranteed structured output — no regex parsing of free-form text.

```python
# Example: the MergeDescription signature
class MergeDescription(dspy.Signature):
    """Analyze a code diff and reverse-engineer the task that produced it."""

    diff: str = dspy.InputField(desc="Unified diff")
    branch_name: str = dspy.InputField(desc="Git branch name")
    commit_messages: str = dspy.InputField(desc="Commit messages")
    file_list: str = dspy.InputField(desc="Changed files")

    title: str = dspy.OutputField(desc="One-line task title")
    description: str = dspy.OutputField(desc="2-5 sentence task description")
    change_type: str = dspy.OutputField(desc="bugfix|feature|refactor|test|docs|chore")
    difficulty: str = dspy.OutputField(desc="easy|medium|hard")
    languages: list[str] = dspy.OutputField(desc="Programming languages")
```

## Related Work

This project builds on ideas from:

| Paper | What we take from it |
|-------|---------------------|
| [CommitPack](https://arxiv.org/abs/2308.07124) (OctoPack, 2023) | Proved commit-based fine-tuning works. We go further with PR-level extraction and synthetic descriptions. |
| [SWE-bench](https://arxiv.org/abs/2310.06770) (2023) | Issue→patch format. Template for our SFT output. |
| [Multi-SWE-RL](https://arxiv.org/abs/2504.02605) (2025) | RL training from issue-resolving. Validates our test-as-reward approach. |
| [DeepSeek-R1](https://arxiv.org/abs/2501.12948) (2025) | Pure RL with test-pass as verifiable reward. |
| [Self-Instruct](https://arxiv.org/abs/2212.10560) (2022) | Generating synthetic instructions from LLM output. Foundation for our description generation. |
| [StarCoder 2](https://arxiv.org/abs/2402.19173) (2024) | Used GitHub PRs as training data. Validates PRs as valuable signal. |

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A local git repository to extract from
- An LLM API key or OAuth login (for enrichment stage only — extraction and filtering work without it)

## Development

```bash
uv sync --group dev
uv run ruff check src/ tests/     # Lint
uv run ruff format src/ tests/    # Format
uv run pytest                     # Test
```

## License

MIT
