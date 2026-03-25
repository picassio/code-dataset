# code-dataset

Extract training datasets (SFT, DPO, RL) from local git repository history for fine-tuning or reinforcement learning of code LLMs.

## Features

- **Git extraction**: Detects both merge commits and squash merges
- **Quality filtering**: Removes bots, trivial changes, secrets/PII, duplicates
- **LLM enrichment**: Generates synthetic task descriptions via DSPy when commit messages are poor
- **Multiple output formats**: SFT (instruction→patch), DPO (preference pairs), RL (with test verification)
- **Multi-repo support**: Process multiple repositories, combine or keep separate
- **OAuth authentication**: Anthropic, Google Gemini — no LiteLLM dependency

## Quick Start

```bash
# Install
uv sync

# Authenticate with an LLM provider
uv run code-dataset auth login anthropic

# Extract from a repo
uv run code-dataset run /path/to/your/repo

# Or run stages individually
uv run code-dataset extract /path/to/repo --output raw.jsonl
uv run code-dataset filter raw.jsonl --output filtered.jsonl
uv run code-dataset enrich filtered.jsonl --output enriched.jsonl
uv run code-dataset format enriched.jsonl --output-dir ./output
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and adjust settings.
Copy `.env.example` to `.env` for API keys.

See [PLAN.md](PLAN.md) for the full architecture and design decisions.
See [AGENTS.md](AGENTS.md) for agent/contributor instructions.
