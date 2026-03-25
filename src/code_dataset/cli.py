"""CLI entry point for code-dataset.

Usage:
    code-dataset run /path/to/repo
    code-dataset extract /path/to/repo --output raw.jsonl
    code-dataset filter raw.jsonl --output filtered.jsonl
    code-dataset enrich filtered.jsonl --output enriched.jsonl
    code-dataset format enriched.jsonl --output-dir ./output
    code-dataset auth login anthropic
    code-dataset config init
    code-dataset stats /path/to/repo
    code-dataset preview /path/to/repo -n 5
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import GLOBAL_CONFIG_DIR, Config, init_config_dir

app = typer.Typer(
    name="code-dataset",
    help="Extract training datasets (SFT, DPO, RL) from git repository history.",
    no_args_is_help=True,
)
auth_app = typer.Typer(name="auth", help="OAuth authentication for LLM providers.", no_args_is_help=True)
config_app = typer.Typer(name="config", help="Configuration management.", no_args_is_help=True)
app.add_typer(auth_app)
app.add_typer(config_app)

console = Console()


def _setup_logging(config: Config) -> None:
    """Configure logging from config settings."""
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if config.log_file:
        handlers.append(logging.FileHandler(config.log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def _resolve_repos(
    repos: list[str] | None,
    config: Config,
) -> list[dict]:
    """Resolve repository list from CLI args or config."""
    if repos:
        return [
            {"path": str(Path(r).expanduser().resolve()), "name": Path(r).name, "main_branch": "main"} for r in repos
        ]
    repo_list = config.repos
    if not repo_list:
        console.print("[red]No repositories specified. Use CLI args or config.yaml.[/red]")
        raise typer.Exit(1)
    return repo_list


# =============================================================================
# Auth commands
# =============================================================================


@auth_app.command("login")
def auth_login(
    provider: Annotated[str, typer.Argument(help="Provider: anthropic, google")] = "anthropic",
) -> None:
    """Login with OAuth (opens browser)."""
    from .oauth import AuthenticationError, authenticate

    try:
        console.print(f"[dim]Authenticating with {provider}...[/dim]")
        credentials = authenticate(provider)
        console.print(f"\n[green]✓ Logged in to {provider}[/green]")
        if credentials.email:
            console.print(f"  Email: {credentials.email}")
        if credentials.project_id:
            console.print(f"  Project: {credentials.project_id}")
        expires = datetime.fromtimestamp(credentials.expires_at, UTC)
        console.print(f"  Expires: {expires:%Y-%m-%d %H:%M:%S UTC}")
    except AuthenticationError as e:
        console.print(f"[red]Login failed: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Login cancelled[/yellow]")
        raise typer.Exit(130)


@auth_app.command("logout")
def auth_logout(
    provider: Annotated[str, typer.Argument(help="Provider: anthropic, google")] = "anthropic",
) -> None:
    """Logout and delete stored credentials."""
    from .oauth import revoke_credentials

    if revoke_credentials(provider):
        console.print(f"[green]✓ Logged out from {provider}[/green]")
    else:
        console.print(f"[dim]No credentials found for {provider}[/dim]")


@auth_app.command("status")
def auth_status() -> None:
    """Show authentication status for all providers."""
    from .oauth import get_credentials, list_providers

    table = Table(title="OAuth Authentication Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Status")
    table.add_column("Email")
    table.add_column("Expires")

    for provider in list_providers():
        creds = get_credentials(provider)
        if creds:
            status = "[yellow]Expired[/yellow]" if creds.is_expired else "[green]Authenticated[/green]"
            email = creds.email or "-"
            expires = datetime.fromtimestamp(creds.expires_at, UTC)
            expires_str = f"{expires:%Y-%m-%d %H:%M}"
        else:
            status = "[dim]Not authenticated[/dim]"
            email = "-"
            expires_str = "-"
        table.add_row(provider, status, email, expires_str)

    console.print(table)


# =============================================================================
# Config commands
# =============================================================================


@config_app.command("init")
def config_init() -> None:
    """Create default config files."""
    path = init_config_dir()
    console.print(f"[green]✓ Config directory initialized at {path}[/green]")
    console.print(f"  Config: {path / 'config.yaml'}")
    console.print(f"  Secrets: {path / '.env'}")


@config_app.command("show")
def config_show(
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="Config file")] = None,
) -> None:
    """Display current effective configuration."""
    config = Config(config_file=config_file)
    settings = {
        "llm": {
            "provider": config.llm_provider,
            "model": config.llm_model,
            "temperature": config.llm_temperature,
            "max_tokens": config.llm_max_tokens,
            "max_calls": config.llm_max_calls,
        },
        "extraction": {
            "merge_strategy": config.merge_strategy,
            "min_diff_lines": config.min_diff_lines,
            "max_diff_lines": config.max_diff_lines,
        },
        "output": {
            "dir": str(config.output_dir),
            "mode": config.output_mode,
            "formats": config.output_formats,
        },
        "repos": config.repos,
    }
    import yaml

    console.print(yaml.dump(settings, default_flow_style=False, sort_keys=False))


@config_app.command("edit")
def config_edit() -> None:
    """Open config file in editor."""
    config_path = GLOBAL_CONFIG_DIR / "config.yaml"
    if not config_path.exists():
        init_config_dir()
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(config_path)])


# =============================================================================
# Extract command
# =============================================================================


@app.command("extract")
def extract_cmd(
    repos: Annotated[Optional[list[str]], typer.Argument(help="Repository paths")] = None,
    output: Annotated[Path, typer.Option("--output", "-o", help="Output JSONL file")] = Path("raw_merges.jsonl"),
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="Config file")] = None,
    branch: Annotated[Optional[str], typer.Option("--branch", "-b", help="Main branch name")] = None,
) -> None:
    """Stage 1: Extract merge records from git repositories."""
    from .extraction.git_extractor import extract_repo, write_records

    config = Config(config_file=config_file)
    _setup_logging(config)

    repo_list = _resolve_repos(repos, config)
    all_records = []

    for repo_info in repo_list:
        repo_path = repo_info.get("path", repo_info) if isinstance(repo_info, dict) else repo_info
        repo_name = repo_info.get("name") if isinstance(repo_info, dict) else None
        main_branch = branch or (repo_info.get("main_branch", "main") if isinstance(repo_info, dict) else "main")

        console.print(f"[cyan]Extracting from {repo_path}...[/cyan]")
        records = extract_repo(repo_path, repo_name=repo_name, main_branch=main_branch, config=config)
        all_records.extend(records)
        console.print(f"  Found {len(records)} merge records")

    write_records(all_records, output)
    console.print(f"\n[green]✓ Wrote {len(all_records)} records to {output}[/green]")


# =============================================================================
# Filter command
# =============================================================================


@app.command("filter")
def filter_cmd(
    input_file: Annotated[Path, typer.Argument(help="Input JSONL file")] = Path("raw_merges.jsonl"),
    output: Annotated[Path, typer.Option("--output", "-o", help="Output JSONL file")] = Path("filtered_merges.jsonl"),
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="Config file")] = None,
) -> None:
    """Stage 2: Filter merge records (remove bots, trivial changes, secrets)."""
    from .extraction.git_extractor import read_records, write_records
    from .filtering.dedup import deduplicate
    from .filtering.quality_filter import filter_records

    config = Config(config_file=config_file)
    _setup_logging(config)

    records = read_records(input_file)
    console.print(f"[cyan]Loaded {len(records)} records from {input_file}[/cyan]")

    filtered = filter_records(records, config)

    if config.dedup_enabled:
        filtered = deduplicate(filtered)

    write_records(filtered, output)
    console.print(f"[green]✓ Kept {len(filtered)}/{len(records)} records → {output}[/green]")


# =============================================================================
# Enrich command
# =============================================================================


@app.command("enrich")
def enrich_cmd(
    input_file: Annotated[Path, typer.Argument(help="Input JSONL file")] = Path("filtered_merges.jsonl"),
    output: Annotated[Path, typer.Option("--output", "-o", help="Output JSONL file")] = Path("enriched_merges.jsonl"),
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="Config file")] = None,
) -> None:
    """Stage 3: Enrich records with LLM-generated descriptions (uses DSPy)."""
    import dspy

    from .enrichment.classifier import classify_records
    from .enrichment.description_gen import enrich_records
    from .enrichment.quality_scorer import score_records
    from .extraction.git_extractor import read_records, write_records
    from .lm.factory import create_lm

    config = Config(config_file=config_file)
    _setup_logging(config)

    # Setup DSPy with our LM
    lm = create_lm(config)
    dspy.configure(lm=lm)
    console.print(f"[cyan]Using LLM: {config.llm_provider}/{config.llm_model}[/cyan]")

    records = read_records(input_file)
    console.print(f"[cyan]Loaded {len(records)} records from {input_file}[/cyan]")

    # Score existing descriptions
    if config.generate_descriptions:
        console.print("[dim]Scoring description quality...[/dim]")
        good, needs_enrichment = score_records(records, config.description_quality_threshold)
        console.print(f"  {len(good)} have good descriptions, {len(needs_enrichment)} need enrichment")

        # Generate descriptions for those that need it
        if needs_enrichment:
            console.print("[dim]Generating synthetic descriptions...[/dim]")
            enrich_records(needs_enrichment, max_calls=config.llm_max_calls, skip_if_enriched=config.skip_if_enriched)

        records = good + needs_enrichment
    else:
        # Just use original messages as descriptions
        for r in records:
            if not r.description:
                r.description = r.merge_message
                r.title = r.merge_message.split("\n")[0]
                r.description_source = "original"

    # Classify type and difficulty
    if config.classify_type or config.classify_difficulty:
        console.print("[dim]Classifying change types and difficulty...[/dim]")
        classify_records(records, max_calls=config.llm_max_calls)

    write_records(records, output)
    console.print(f"[green]✓ Enriched {len(records)} records → {output}[/green]")


# =============================================================================
# Format command
# =============================================================================


@app.command("format")
def format_cmd(
    input_file: Annotated[Path, typer.Argument(help="Input JSONL file")] = Path("enriched_merges.jsonl"),
    output_dir: Annotated[Optional[Path], typer.Option("--output-dir", "-d", help="Output directory")] = None,
    formats: Annotated[Optional[str], typer.Option("--formats", "-f", help="Comma-separated: sft,dpo,rl")] = None,
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="Config file")] = None,
) -> None:
    """Stage 4: Format enriched records into training datasets."""
    from .extraction.git_extractor import read_records
    from .formatting.dpo_formatter import write_dpo_dataset
    from .formatting.rl_formatter import write_rl_dataset
    from .formatting.sft_formatter import write_sft_dataset
    from .utils.stats import compute_stats, format_stats_table, write_stats

    config = Config(config_file=config_file)
    _setup_logging(config)

    out_dir = output_dir or config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    fmt_list = formats.split(",") if formats else config.output_formats

    records = read_records(input_file)
    console.print(f"[cyan]Loaded {len(records)} records from {input_file}[/cyan]")

    max_ctx = config.max_context_tokens

    if "sft" in fmt_list:
        sft_count = write_sft_dataset(records, out_dir / "sft_dataset.jsonl", max_ctx)
        console.print(f"  SFT: {sft_count} records")

    if "dpo" in fmt_list:
        dpo_count = write_dpo_dataset(records, out_dir / "dpo_dataset.jsonl")
        console.print(f"  DPO: {dpo_count} pairs")

    if "rl" in fmt_list:
        rl_count = write_rl_dataset(records, out_dir / "rl_dataset.jsonl", max_ctx)
        console.print(f"  RL: {rl_count} records (with tests)")

    # Write stats
    stats = compute_stats(records)
    write_stats(stats, out_dir / "report.json")
    console.print(f"\n{format_stats_table(stats)}")
    console.print(f"\n[green]✓ Datasets written to {out_dir}/[/green]")


# =============================================================================
# Run command (full pipeline)
# =============================================================================


@app.command("run")
def run_cmd(
    repos: Annotated[Optional[list[str]], typer.Argument(help="Repository paths")] = None,
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="Config file")] = None,
    combine: Annotated[bool, typer.Option("--combine", help="Combine all repos into one dataset")] = False,
    branch: Annotated[Optional[str], typer.Option("--branch", "-b", help="Main branch name")] = None,
) -> None:
    """Run the full pipeline: extract → filter → enrich → format."""
    import dspy

    from .enrichment.classifier import classify_records
    from .enrichment.description_gen import enrich_records
    from .enrichment.quality_scorer import score_records
    from .extraction.git_extractor import extract_repo
    from .filtering.dedup import deduplicate
    from .filtering.quality_filter import filter_records
    from .lm.factory import create_lm

    config = Config(
        config_file=config_file,
        cli_overrides={"output.mode": "combine" if combine else config_file and None},
    )
    _setup_logging(config)

    repo_list = _resolve_repos(repos, config)
    output_mode = "combine" if combine else config.output_mode
    out_dir = config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    max_ctx = config.max_context_tokens
    fmt_list = config.output_formats

    # Setup LLM
    lm = create_lm(config)
    dspy.configure(lm=lm)
    console.print(f"[cyan]LLM: {config.llm_provider}/{config.llm_model}[/cyan]")

    all_records: list = []

    for repo_info in repo_list:
        repo_path = repo_info.get("path", repo_info) if isinstance(repo_info, dict) else repo_info
        repo_name = repo_info.get("name") if isinstance(repo_info, dict) else Path(repo_path).name
        main_branch = branch or (repo_info.get("main_branch", "main") if isinstance(repo_info, dict) else "main")

        console.print(f"\n[bold cyan]═══ {repo_name} ═══[/bold cyan]")

        # Stage 1: Extract
        console.print("[dim]Stage 1: Extracting...[/dim]")
        records = extract_repo(repo_path, repo_name=repo_name, main_branch=main_branch, config=config)
        console.print(f"  Extracted {len(records)} merge records")

        if not records:
            console.print("  [yellow]No records found, skipping.[/yellow]")
            continue

        # Stage 2: Filter
        console.print("[dim]Stage 2: Filtering...[/dim]")
        records = filter_records(records, config)
        if config.dedup_enabled:
            records = deduplicate(records)
        console.print(f"  Kept {len(records)} records after filtering")

        if not records:
            console.print("  [yellow]All records filtered out, skipping.[/yellow]")
            continue

        # Stage 3: Enrich
        console.print("[dim]Stage 3: Enriching...[/dim]")
        if config.generate_descriptions:
            good, needs = score_records(records, config.description_quality_threshold)
            if needs:
                enrich_records(needs, max_calls=config.llm_max_calls, skip_if_enriched=config.skip_if_enriched)
            records = good + needs
        else:
            for r in records:
                if not r.description:
                    r.description = r.merge_message
                    r.title = r.merge_message.split("\n")[0]
                    r.description_source = "original"

        if config.classify_type or config.classify_difficulty:
            classify_records(records, max_calls=config.llm_max_calls)

        if output_mode == "combine":
            all_records.extend(records)
        else:
            # Write per-repo datasets
            repo_dir = out_dir / repo_name
            _write_datasets(records, repo_dir, fmt_list, max_ctx)
            console.print(f"  [green]✓ Written to {repo_dir}/[/green]")

    # Write combined datasets
    if output_mode == "combine" and all_records:
        console.print(f"\n[bold cyan]═══ Combined ({len(all_records)} records) ═══[/bold cyan]")
        _write_datasets(all_records, out_dir, fmt_list, max_ctx)

    console.print(f"\n[green]✓ Pipeline complete. Output: {out_dir}/[/green]")


def _write_datasets(records: list, out_dir: Path, fmt_list: list[str], max_ctx: int) -> None:
    """Write all dataset formats and stats."""
    from .formatting.dpo_formatter import write_dpo_dataset
    from .formatting.rl_formatter import write_rl_dataset
    from .formatting.sft_formatter import write_sft_dataset
    from .utils.stats import compute_stats, format_stats_table, write_stats

    if "sft" in fmt_list:
        n = write_sft_dataset(records, out_dir / "sft_dataset.jsonl", max_ctx)
        console.print(f"  SFT: {n} records")
    if "dpo" in fmt_list:
        n = write_dpo_dataset(records, out_dir / "dpo_dataset.jsonl")
        console.print(f"  DPO: {n} pairs")
    if "rl" in fmt_list:
        n = write_rl_dataset(records, out_dir / "rl_dataset.jsonl", max_ctx)
        console.print(f"  RL: {n} records")

    stats = compute_stats(records)
    write_stats(stats, out_dir / "report.json")
    console.print(f"\n{format_stats_table(stats)}")


# =============================================================================
# Stats command
# =============================================================================


@app.command("stats")
def stats_cmd(
    path: Annotated[str, typer.Argument(help="Path to repo or JSONL file")],
) -> None:
    """Show statistics for a repository or dataset file."""
    from .utils.stats import compute_stats, format_stats_table

    p = Path(path)

    if p.suffix == ".jsonl":
        from .extraction.git_extractor import read_records

        records = read_records(p)
    elif (p / ".git").exists():
        from .extraction.git_extractor import extract_repo

        config = Config()
        _setup_logging(config)
        records = extract_repo(p, config=config)
    else:
        console.print(f"[red]{path} is not a git repo or JSONL file[/red]")
        raise typer.Exit(1)

    stats = compute_stats(records)
    console.print(format_stats_table(stats))


# =============================================================================
# Preview command
# =============================================================================


@app.command("preview")
def preview_cmd(
    repo_path: Annotated[str, typer.Argument(help="Repository path")],
    n: Annotated[int, typer.Option("--limit", "-n", help="Number of records to show")] = 5,
    branch: Annotated[Optional[str], typer.Option("--branch", "-b", help="Main branch")] = None,
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="Config file")] = None,
) -> None:
    """Preview what would be extracted from a repository (dry run)."""
    from .extraction.git_extractor import extract_repo

    config = Config(config_file=config_file)
    _setup_logging(config)

    main_branch = branch or "main"
    records = extract_repo(repo_path, main_branch=main_branch, config=config)

    console.print(f"\n[cyan]Found {len(records)} merge records. Showing first {min(n, len(records))}:[/cyan]\n")

    for record in records[:n]:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold")
        table.add_column()
        table.add_row("ID", record.id)
        table.add_row("Type", record.merge_type.value)
        table.add_row("Message", record.merge_message[:120])
        table.add_row("Branch", record.branch_name or "-")
        table.add_row("Files", str(record.num_files))
        table.add_row("Changes", f"+{record.insertions}/-{record.deletions}")
        table.add_row("Authors", ", ".join(record.authors))
        table.add_row("Date", record.timestamp.strftime("%Y-%m-%d %H:%M") if record.timestamp else "-")
        table.add_row("Has Tests", "✓" if record.has_test_changes else "✗")
        console.print(table)
        console.print()


if __name__ == "__main__":
    app()
