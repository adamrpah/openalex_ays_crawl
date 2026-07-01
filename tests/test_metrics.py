from __future__ import annotations

import pandas as pd

from ays_bibliometrics.metrics import researcher_metrics


def test_researcher_metrics_allows_blank_research_center() -> None:
    works = pd.DataFrame(
        [
            {
                "work_id": "W1",
                "cited_by_count": 12,
                "publication_year": 2024,
            }
        ]
    )
    authorships = pd.DataFrame(
        [
            {
                "work_id": "W1",
                "matched_author_id": "A1",
                "matched_person_name": "Adam Pah",
                "person_department": "Criminal Justice and Criminology",
                "person_research_center": None,
            }
        ]
    )

    metrics = researcher_metrics(works, authorships)

    assert metrics.loc[0, "department"] == "Criminal Justice and Criminology"
    assert metrics.loc[0, "research_center"] == ""


def test_researcher_metrics_combines_multiple_openalex_ids_per_person() -> None:
    works = pd.DataFrame(
        [
            {"work_id": "W1", "cited_by_count": 10, "publication_year": 2023},
            {"work_id": "W2", "cited_by_count": 5, "publication_year": 2024},
        ]
    )
    authorships = pd.DataFrame(
        [
            {
                "work_id": "W1",
                "matched_author_id": "A1",
                "matched_person_name": "Alex Smith",
                "person_department": "Economics",
                "person_research_center": "",
            },
            {
                "work_id": "W1",
                "matched_author_id": "A2",
                "matched_person_name": "Alex Smith",
                "person_department": "Economics",
                "person_research_center": "",
            },
            {
                "work_id": "W2",
                "matched_author_id": "A2",
                "matched_person_name": "Alex Smith",
                "person_department": "Economics",
                "person_research_center": "",
            },
        ]
    )

    metrics = researcher_metrics(works, authorships)

    assert len(metrics) == 1
    assert metrics.loc[0, "person_name"] == "Alex Smith"
    assert metrics.loc[0, "author_id"] == "A1; A2"
    assert metrics.loc[0, "publications"] == 2
    assert metrics.loc[0, "citations"] == 15
