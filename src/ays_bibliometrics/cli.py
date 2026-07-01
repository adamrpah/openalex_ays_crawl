from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer

from .cache import ResponseCache
from .config import AppConfig, ensure_directories, load_config
from .logging import configure_logging
from .matching import build_author_matches, filter_site_matches, load_approved_authors
from .metrics import (
    center_summaries,
    department_summaries,
    publication_metrics,
    researcher_metrics,
    top_faculty,
    top_journals,
    top_papers,
    year_summaries,
)
from .openalex import OpenAlexClient
from .reports import write_excel_report, write_metrics
from .roster import get_roster_provider
from .util import write_csv
from .works import deduplicate_works, download_works

app = typer.Typer(help="AYS bibliometric reporting pipeline.")


def bootstrap(config_path: Path, verbose: bool) -> AppConfig:
    config = load_config(config_path)
    ensure_directories(config)
    configure_logging(config.paths.log_file, verbose=verbose)
    return config


def openalex_client(config: AppConfig) -> OpenAlexClient:
    return OpenAlexClient(config.openalex, ResponseCache(config.paths.cache_dir, "openalex"))


@app.command("build-roster")
def build_roster(
    config_path: Path = typer.Option(Path("config.yaml"), "--config"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    config = bootstrap(config_path, verbose)
    client = openalex_client(config) if config.roster.provider == "openalex_institution" else None
    provider = get_roster_provider(config, client)
    roster = provider.build()
    out = config.paths.output_dir / "roster.csv"
    write_csv(roster, out)
    typer.echo(f"Wrote {len(roster)} roster rows to {out}")


@app.command("match-authors")
def match_authors(
    config_path: Path = typer.Option(Path("config.yaml"), "--config"),
    roster_path: Path | None = typer.Option(None, "--roster"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    config = bootstrap(config_path, verbose)
    roster_file = roster_path or config.paths.output_dir / "roster.csv"
    roster = pd.read_csv(roster_file)
    matches = build_author_matches(roster, openalex_client(config), config)
    site_matches = filter_site_matches(matches)
    all_out = config.paths.output_dir / "all_matches.xlsx"
    site_out = config.paths.output_dir / "site_matches.xlsx"
    with pd.ExcelWriter(all_out, engine="openpyxl") as writer:
        matches.to_excel(writer, index=False, sheet_name="Review")
    with pd.ExcelWriter(site_out, engine="openpyxl") as writer:
        site_matches.to_excel(writer, index=False, sheet_name="Review")
    typer.echo(
        f"Wrote {len(matches)} candidate rows to {all_out} and "
        f"{len(site_matches)} site-matched rows to {site_out}. Review include before continuing."
    )


@app.command("download-works")
def download_works_command(
    config_path: Path = typer.Option(Path("config.yaml"), "--config"),
    matches_path: Path | None = typer.Option(None, "--matches"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    config = bootstrap(config_path, verbose)
    approved = load_approved_authors(matches_path or config.paths.output_dir / "site_matches.xlsx")
    approved_path = config.paths.output_dir / "approved_authors.csv"
    write_csv(approved, approved_path)
    works, authorships = download_works(
        approved,
        openalex_client(config),
        config.paths.output_dir / "works.parquet",
        config.paths.output_dir / "works_authorships.parquet",
    )
    deduped = deduplicate_works(works, authorships)
    deduped.to_parquet(config.paths.output_dir / "works_deduplicated.parquet", index=False)
    typer.echo(f"Wrote {len(works)} author-work rows and {len(deduped)} unique works.")


@app.command("compute-metrics")
def compute_metrics_command(
    config_path: Path = typer.Option(Path("config.yaml"), "--config"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    config = bootstrap(config_path, verbose)
    works = pd.read_parquet(config.paths.output_dir / "works.parquet")
    authorships = pd.read_parquet(config.paths.output_dir / "works_authorships.parquet")
    deduped_path = config.paths.output_dir / "works_deduplicated.parquet"
    deduped = pd.read_parquet(deduped_path) if deduped_path.exists() else deduplicate_works(works, authorships)
    metrics = compute_all_metrics(works, authorships, deduped)
    write_metrics(metrics, config.paths.output_dir / "metrics")
    typer.echo(f"Wrote metrics to {config.paths.output_dir / 'metrics'}")


@app.command("generate-report")
def generate_report_command(
    config_path: Path = typer.Option(Path("config.yaml"), "--config"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    config = bootstrap(config_path, verbose)
    metrics_dir = config.paths.output_dir / "metrics"
    metrics = {
        path.stem: pd.read_csv(path)
        for path in metrics_dir.glob("*.csv")
    }
    works_path = config.paths.output_dir / "works_deduplicated.parquet"
    works = pd.read_parquet(works_path) if works_path.exists() else pd.DataFrame()
    report_path = config.paths.output_dir / "ays_bibliometrics_report.xlsx"
    write_excel_report(metrics, works, report_path)
    from .plots import generate_figures

    generate_figures(metrics, config.paths.output_dir / "figures")
    typer.echo(f"Wrote report to {report_path}")


@app.command("run-all")
def run_all(
    config_path: Path = typer.Option(Path("config.yaml"), "--config"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    config = bootstrap(config_path, verbose)
    roster_file = config.paths.output_dir / "roster.csv"
    matches_file = config.paths.output_dir / "site_matches.xlsx"
    if not roster_file.exists():
        build_roster(config_path, verbose)
    if not matches_file.exists():
        match_authors(config_path, None, verbose)
        typer.echo(f"Stopped for manual review. Set include=TRUE in {matches_file}, then rerun run-all.")
        raise typer.Exit()
    try:
        load_approved_authors(matches_file)
    except ValueError as exc:
        typer.echo(f"Stopped for manual review: {exc}")
        typer.echo(f"Update {matches_file}, then rerun run-all.")
        raise typer.Exit(code=1) from exc
    download_works_command(config_path, matches_file, verbose)
    compute_metrics_command(config_path, verbose)
    generate_report_command(config_path, verbose)
    review_file = config.paths.output_dir / "site_matches.xlsx"
    typer.echo(f"Completed pipeline using reviewed matches from {review_file}.")


def compute_all_metrics(works: pd.DataFrame, authorships: pd.DataFrame, deduped: pd.DataFrame) -> dict[str, pd.DataFrame]:
    researchers = researcher_metrics(works, authorships)
    return {
        "researcher_metrics": researchers,
        "publication_metrics": publication_metrics(deduped),
        "department_summaries": department_summaries(researchers),
        "center_summaries": center_summaries(researchers),
        "year_summaries": year_summaries(deduped),
        "top_journals": top_journals(deduped),
        "top_papers": top_papers(deduped),
        "top_faculty": top_faculty(researchers),
    }


if __name__ == "__main__":
    app()
