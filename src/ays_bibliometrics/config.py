from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PathConfig:
    root: Path
    data_dir: Path
    cache_dir: Path
    output_dir: Path
    log_file: Path


@dataclass(frozen=True)
class OpenAlexConfig:
    base_url: str
    api_key: str
    polite_pool_email: str
    per_page: int = 200
    rate_limit_seconds: float = 0.12


@dataclass(frozen=True)
class RosterConfig:
    provider: str
    website_url: str
    input_csv: Path
    openalex_institution_id: str
    manual_people: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MatchingConfig:
    candidates_per_person: int = 5
    min_auto_confidence: float = 0.92
    ambiguity_margin: float = 0.08
    institution_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AppConfig:
    root: Path
    email: str
    paths: PathConfig
    openalex: OpenAlexConfig
    roster: RosterConfig
    matching: MatchingConfig
    departments: list[str]
    centers: list[str]
    raw: dict[str, Any]


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    path = Path(config_path).resolve()
    root = path.parent
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    raw_paths = raw.get("paths", {})
    paths = PathConfig(
        root=root,
        data_dir=_resolve(root, raw_paths.get("data_dir", "data")),
        cache_dir=_resolve(root, raw_paths.get("cache_dir", "cache")),
        output_dir=_resolve(root, raw_paths.get("output_dir", "output")),
        log_file=_resolve(root, raw_paths.get("log_file", "output/run.log")),
    )

    raw_openalex = raw.get("openalex", {})
    openalex = OpenAlexConfig(
        base_url=raw_openalex.get("base_url", "https://api.openalex.org").rstrip("/"),
        api_key=str(raw_openalex.get("api_key", "") or ""),
        polite_pool_email=raw_openalex.get("polite_pool_email", raw.get("email", "")),
        per_page=int(raw_openalex.get("per_page", 200)),
        rate_limit_seconds=float(raw_openalex.get("rate_limit_seconds", 0.12)),
    )

    raw_roster = raw.get("roster", {})
    roster = RosterConfig(
        provider=raw_roster.get("provider", "ays_website"),
        website_url=raw_roster.get("website_url", "https://aysps.gsu.edu/profile/"),
        input_csv=_resolve(root, raw_roster.get("input_csv", "data/manual_roster.csv")),
        openalex_institution_id=raw_roster.get("openalex_institution_id", "https://openalex.org/I1341412227"),
        manual_people=list(raw_roster.get("manual_people", [])),
    )

    raw_matching = raw.get("matching", {})
    matching = MatchingConfig(
        candidates_per_person=int(raw_matching.get("candidates_per_person", 5)),
        min_auto_confidence=float(raw_matching.get("min_auto_confidence", 0.92)),
        ambiguity_margin=float(raw_matching.get("ambiguity_margin", 0.08)),
        institution_keywords=list(raw_matching.get("institution_keywords", [])),
    )

    return AppConfig(
        root=root,
        email=raw.get("email", ""),
        paths=paths,
        openalex=openalex,
        roster=roster,
        matching=matching,
        departments=list(raw.get("departments", [])),
        centers=list(raw.get("centers", [])),
        raw=raw,
    )


def ensure_directories(config: AppConfig) -> None:
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    config.paths.cache_dir.mkdir(parents=True, exist_ok=True)
    config.paths.output_dir.mkdir(parents=True, exist_ok=True)
    config.paths.log_file.parent.mkdir(parents=True, exist_ok=True)
