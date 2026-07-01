from __future__ import annotations

from pathlib import Path

import pandas as pd

from ays_bibliometrics.config import (
    AppConfig,
    MatchingConfig,
    OpenAlexConfig,
    PathConfig,
    RosterConfig,
)
from ays_bibliometrics.matching import (
    build_author_matches,
    filter_site_matches,
    load_approved_authors,
    observed_institutions,
)
from ays_bibliometrics.roster import normalize_roster
from ays_bibliometrics.util import clean_person_name


def test_clean_person_name_strips_degree_and_site_title() -> None:
    assert (
        clean_person_name("E. Kathleen Adams, PhD | Winship Cancer Institute of Emory University")
        == "E. Kathleen Adams"
    )
    assert clean_person_name("James L. Maddex, Jr.") == "James L. Maddex, Jr."


def test_normalize_roster_cleans_names() -> None:
    roster = normalize_roster(
        pd.DataFrame(
            [
                {
                    "name": "E. Kathleen Adams, PhD | Winship Cancer Institute of Emory University",
                    "profile_url": "https://aysps.gsu.edu/profile/kathleen-adams/",
                }
            ]
        ),
        source="ays_website",
    )

    assert roster.loc[0, "name"] == "E. Kathleen Adams"


def test_build_author_matches_searches_with_cleaned_name() -> None:
    client = RecordingClient()
    roster = pd.DataFrame(
        [
            {
                "name": "E. Kathleen Adams, PhD | Winship Cancer Institute of Emory University",
                "title": "",
                "department": "",
                "research_center": "",
                "email": "",
                "profile_url": "",
            }
        ]
    )

    matches = build_author_matches(roster, client, _config())

    assert client.queries == ["E. Kathleen Adams"]
    assert matches.loc[0, "person_name"] == "E. Kathleen Adams"
    assert "observed_institutions" in matches.columns


def test_filter_site_matches_uses_observed_institutions() -> None:
    matches = build_author_matches(
        pd.DataFrame([_person("Alex Smith")]), RecordingClient(), _config()
    )
    site_matches = filter_site_matches(matches)

    assert len(matches) == 2
    assert len(site_matches) == 1
    assert site_matches.loc[0, "display_name"] == "Alex Smith"
    assert site_matches.loc[0, "site_match"]
    assert "Georgia State University" in site_matches.loc[0, "observed_institutions"]


def test_observed_institutions_handles_openalex_affiliations() -> None:
    candidate = {
        "last_known_institutions": [{"display_name": "Andrew Young School of Policy Studies"}],
        "affiliations": [
            {"institution": {"display_name": "Georgia State University"}},
            {"institution": {"display_name": "Georgia State University"}},
        ],
    }

    assert observed_institutions(candidate) == [
        "Andrew Young School of Policy Studies",
        "Georgia State University",
    ]


def test_load_approved_authors_allows_multiple_ids_for_same_person(tmp_path) -> None:
    matches_path = tmp_path / "matches.xlsx"
    pd.DataFrame(
        [
            {"include": True, "person_name": "Alex Smith", "author_id": "A1"},
            {"include": True, "person_name": "Alex Smith", "author_id": "A2"},
        ]
    ).to_excel(matches_path, index=False)

    approved = load_approved_authors(matches_path)

    assert approved["person_name"].tolist() == ["Alex Smith", "Alex Smith"]
    assert approved["author_id"].tolist() == ["A1", "A2"]


class RecordingClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search_authors(self, query: str, per_page: int = 5) -> list[dict]:
        self.queries.append(query)
        return [
            {
                "display_name": query,
                "id": "https://openalex.org/A1",
                "last_known_institutions": [{"display_name": "Georgia State University"}],
                "affiliations": [
                    {"institution": {"display_name": "Georgia State University"}, "years": [2025]}
                ],
                "x_concepts": [],
                "works_count": 10,
                "cited_by_count": 25,
                "orcid": "",
                "relevance_score": 1.0,
            },
            {
                "display_name": f"{query} Other",
                "id": "https://openalex.org/A2",
                "last_known_institutions": [{"display_name": "Emory University"}],
                "affiliations": [
                    {"institution": {"display_name": "Emory University"}, "years": [2024]}
                ],
                "x_concepts": [],
                "works_count": 10,
                "cited_by_count": 25,
                "orcid": "",
                "relevance_score": 0.9,
            },
        ]


def _person(name: str) -> dict[str, str]:
    return {
        "name": name,
        "title": "",
        "department": "",
        "research_center": "",
        "email": "",
        "profile_url": "",
    }


def _config() -> AppConfig:
    root = Path(".")
    return AppConfig(
        root=root,
        email="",
        paths=PathConfig(
            root=root,
            data_dir=root,
            cache_dir=root,
            output_dir=root,
            log_file=root / "run.log",
        ),
        openalex=OpenAlexConfig(
            base_url="https://api.openalex.org", api_key="", polite_pool_email=""
        ),
        roster=RosterConfig(
            provider="manual",
            website_url="",
            input_csv=root / "roster.csv",
            openalex_institution_id="",
        ),
        matching=MatchingConfig(
            candidates_per_person=5, ambiguity_margin=0.08, institution_keywords=[]
        ),
        departments=[],
        centers=[],
        raw={},
    )
