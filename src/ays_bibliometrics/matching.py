from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any

import pandas as pd
import requests

from .config import AppConfig
from .openalex import OpenAlexClient
from .util import clean_person_name, normalize_name

logger = logging.getLogger(__name__)

SITE_MATCH_KEYWORDS = ("georgia state university", "andrew young school")


def score_candidate(person: pd.Series, candidate: dict[str, Any], config: AppConfig) -> float:
    name_score = SequenceMatcher(
        None, normalize_name(person.get("name", "")), normalize_name(candidate.get("display_name", ""))
    ).ratio()
    institution_text = " ".join(observed_institutions(candidate)).lower()
    institution_score = 1.0 if any(k.lower() in institution_text for k in config.matching.institution_keywords) else 0.0
    stopwords = {"and", "of", "the", "for", "in", "to", "a"}
    department_text = f"{person.get('department', '')} {person.get('research_center', '')}".lower()
    department_tokens = [token for token in department_text.split() if len(token) > 3 and token not in stopwords]
    concepts = " ".join(c.get("display_name", "") for c in candidate.get("x_concepts", [])).lower()
    department_score = 1.0 if department_tokens and any(token in concepts for token in department_tokens) else 0.0
    orcid_score = 1.0 if candidate.get("orcid") else 0.0
    works_score = min(float(candidate.get("works_count") or 0) / 100.0, 1.0)
    score = (
        0.50 * name_score
        + 0.25 * institution_score
        + 0.10 * department_score
        + 0.05 * orcid_score
        + 0.10 * works_score
    )
    return round(score, 4)


def build_author_matches(roster: pd.DataFrame, client: OpenAlexClient, config: AppConfig) -> pd.DataFrame:
    rows = []
    for _, person in roster.iterrows():
        person = person.copy()
        raw_name = person.get("name", "")
        search_name = clean_person_name(raw_name)
        if not search_name:
            logger.warning("author_match_skipped_empty_name", extra={"_person_name": raw_name})
            continue
        if search_name != raw_name:
            logger.warning(
                "author_match_cleaned_name",
                extra={"_person_name": raw_name, "_search_name": search_name},
            )
            person["name"] = search_name
        try:
            candidates = client.search_authors(
                search_name, per_page=config.matching.candidates_per_person
            )
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 400:
                logger.warning(
                    "author_match_bad_request_skipped",
                    extra={"_person_name": raw_name, "_search_name": search_name},
                )
                candidates = []
            else:
                raise
        scored = []
        for candidate in candidates:
            scored.append((score_candidate(person, candidate, config), candidate))
        scored.sort(key=lambda item: item[0], reverse=True)
        top_score = scored[0][0] if scored else 0.0
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        ambiguous = top_score - second_score < config.matching.ambiguity_margin
        for rank, (score, candidate) in enumerate(scored, start=1):
            institutions = observed_institutions(candidate)
            last_known_names = [
                institution.get("display_name", "")
                for institution in _last_known_institutions(candidate)
                if institution.get("display_name", "")
            ]
            rows.append(
                {
                    "include": False,
                    "ambiguous": ambiguous,
                    "site_match": is_site_match(candidate),
                    "rank": rank,
                    "confidence_score": score,
                    "person_name": person.get("name", ""),
                    "person_title": person.get("title", ""),
                    "person_department": person.get("department", ""),
                    "person_research_center": person.get("research_center", ""),
                    "person_email": person.get("email", ""),
                    "person_profile_url": person.get("profile_url", ""),
                    "display_name": candidate.get("display_name", ""),
                    "author_id": candidate.get("id", ""),
                    "institution": "; ".join(last_known_names),
                    "observed_institutions": "; ".join(institutions),
                    "works": candidate.get("works_count", 0),
                    "citations": candidate.get("cited_by_count", 0),
                    "orcid": candidate.get("orcid", ""),
                    "relevance_score": candidate.get("relevance_score", ""),
                }
            )
        if not scored:
            logger.warning("author_match_no_candidates", extra={"_person_name": person.get("name", "")})
    return pd.DataFrame(rows)


def filter_site_matches(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty or "site_match" not in matches.columns:
        return matches.iloc[0:0].copy()
    return matches[matches["site_match"].fillna(False)].reset_index(drop=True)


def observed_institutions(candidate: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for institution in _last_known_institutions(candidate):
        _append_institution_name(names, institution)
    for affiliation in candidate.get("affiliations") or []:
        if isinstance(affiliation, dict):
            _append_institution_name(names, affiliation.get("institution"))
    return names


def is_site_match(candidate: dict[str, Any]) -> bool:
    text = " | ".join(observed_institutions(candidate)).lower()
    return any(keyword in text for keyword in SITE_MATCH_KEYWORDS)


def _last_known_institutions(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    institutions = candidate.get("last_known_institutions")
    if isinstance(institutions, list):
        return [institution for institution in institutions if isinstance(institution, dict)]
    institution = candidate.get("last_known_institution")
    return [institution] if isinstance(institution, dict) else []


def _append_institution_name(names: list[str], institution: Any) -> None:
    if not isinstance(institution, dict):
        return
    name = str(institution.get("display_name", "")).strip()
    if name and name not in names:
        names.append(name)


def load_approved_authors(matches_path) -> pd.DataFrame:
    matches = pd.read_excel(matches_path)
    if "include" not in matches.columns:
        raise ValueError("Reviewed matches file must contain an include column.")
    approved = matches[matches["include"].map(_truthy)].copy()
    if approved.empty:
        raise ValueError(
            "No approved authors found. Review site_matches.xlsx and set include=TRUE."
        )
    approved = approved.drop_duplicates(subset=["person_name", "author_id"])
    reused_author_ids = approved.groupby("author_id")["person_name"].nunique()
    reused_author_ids = reused_author_ids[reused_author_ids > 1]
    if not reused_author_ids.empty:
        ids = ", ".join(str(author_id) for author_id in reused_author_ids.index)
        raise ValueError(f"Same OpenAlex author approved for multiple people: {ids}")
    return approved.reset_index(drop=True)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "t", "1", "yes", "y"}
