from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from .openalex import OpenAlexClient

logger = logging.getLogger(__name__)


def download_works(
    approved: pd.DataFrame,
    client: OpenAlexClient,
    works_path: Path,
    authorships_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if works_path.exists() and authorships_path.exists():
        works = pd.read_parquet(works_path)
        authorships = pd.read_parquet(authorships_path)
        cached_author_ids = set(authorships.get("matched_author_id", pd.Series(dtype=str)).dropna())
        approved_author_ids = set(approved["author_id"].dropna())
        if approved_author_ids.issubset(cached_author_ids):
            logger.info("works_existing_loaded", extra={"_works_path": str(works_path)})
            return works, authorships
        missing = sorted(approved_author_ids - cached_author_ids)
        logger.info(
            "works_cache_missing_approved_authors",
            extra={"_missing_author_count": len(missing)},
        )

    work_rows: list[dict[str, Any]] = []
    authorship_rows: list[dict[str, Any]] = []
    for _, author in tqdm(approved.iterrows(), total=len(approved), desc="Downloading works"):
        author_id = author["author_id"]
        for work in client.iter_works_for_author(author_id):
            work_rows.append(
                flatten_work(
                    work,
                    matched_author_id=author_id,
                    matched_person_name=author["person_name"],
                )
            )
            authorship_rows.append(
                {
                    "work_id": work.get("id", ""),
                    "matched_author_id": author_id,
                    "matched_person_name": author["person_name"],
                    "person_department": author.get("person_department", ""),
                    "person_research_center": author.get("person_research_center", ""),
                }
            )

    works = pd.DataFrame(work_rows)
    authorships = pd.DataFrame(authorship_rows).drop_duplicates()
    works_path.parent.mkdir(parents=True, exist_ok=True)
    authorships_path.parent.mkdir(parents=True, exist_ok=True)
    works.to_parquet(works_path, index=False)
    authorships.to_parquet(authorships_path, index=False)
    return works, authorships


def flatten_work(
    work: dict[str, Any], matched_author_id: str, matched_person_name: str
) -> dict[str, Any]:
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    open_access = work.get("open_access") or {}
    authorships = work.get("authorships") or []
    countries = sorted(
        {
            country
            for authorship in authorships
            for institution in authorship.get("institutions", [])
            for country in [institution.get("country_code")]
            if country
        }
    )
    return {
        "work_id": work.get("id", ""),
        "doi": work.get("doi", ""),
        "title": work.get("title", ""),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date", ""),
        "type": work.get("type", ""),
        "cited_by_count": work.get("cited_by_count", 0),
        "is_oa": open_access.get("is_oa", False),
        "oa_status": open_access.get("oa_status", ""),
        "journal": source.get("display_name", ""),
        "publisher": source.get("host_organization_name", ""),
        "source_id": source.get("id", ""),
        "authorship_count": len(authorships),
        "institution_countries": ";".join(countries),
        "international_collaboration": len([c for c in countries if c != "US"]) > 0,
        "matched_author_id": matched_author_id,
        "matched_person_name": matched_person_name,
    }


def deduplicate_works(works: pd.DataFrame, authorships: pd.DataFrame) -> pd.DataFrame:
    if works.empty:
        return works
    ordered = works.sort_values(["work_id", "cited_by_count"], ascending=[True, False])
    deduped = ordered.drop_duplicates(subset=["work_id"], keep="first").copy()
    matched_people = authorships.groupby("work_id")["matched_person_name"].apply(
        lambda values: "; ".join(sorted(set(values)))
    )
    matched_count = authorships.groupby("work_id")["matched_person_name"].nunique()
    departments = authorships.groupby("work_id")["person_department"].apply(_join_clean_values)
    centers = authorships.groupby("work_id")["person_research_center"].apply(_join_clean_values)
    deduped["ays_matched_authors"] = deduped["work_id"].map(matched_people).fillna("")
    deduped["ays_author_count"] = deduped["work_id"].map(matched_count).fillna(0).astype(int)
    deduped["departments"] = deduped["work_id"].map(departments).fillna("")
    deduped["research_centers"] = deduped["work_id"].map(centers).fillna("")
    return deduped.reset_index(drop=True)


def _join_clean_values(values: pd.Series) -> str:
    cleaned = {
        str(value).strip()
        for value in values
        if pd.notna(value) and str(value).strip()
    }
    return "; ".join(sorted(cleaned))
