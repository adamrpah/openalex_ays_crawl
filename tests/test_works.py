from __future__ import annotations

import pandas as pd

from ays_bibliometrics.works import download_works


def test_download_works_refreshes_cache_when_approved_author_is_missing(tmp_path) -> None:
    works_path = tmp_path / "works.parquet"
    authorships_path = tmp_path / "authorships.parquet"
    pd.DataFrame(
        [
            {
                "work_id": "W1",
                "matched_author_id": "A1",
                "matched_person_name": "Alex Smith",
                "cited_by_count": 1,
                "publication_year": 2024,
            }
        ]
    ).to_parquet(works_path, index=False)
    pd.DataFrame(
        [
            {
                "work_id": "W1",
                "matched_author_id": "A1",
                "matched_person_name": "Alex Smith",
                "person_department": "Economics",
                "person_research_center": "",
            }
        ]
    ).to_parquet(authorships_path, index=False)
    approved = pd.DataFrame(
        [
            {
                "author_id": "A1",
                "person_name": "Alex Smith",
                "person_department": "Economics",
                "person_research_center": "",
            },
            {
                "author_id": "A2",
                "person_name": "Alex Smith",
                "person_department": "Economics",
                "person_research_center": "",
            },
        ]
    )

    works, authorships = download_works(
        approved, RecordingWorksClient(), works_path, authorships_path
    )

    assert sorted(authorships["matched_author_id"].unique()) == ["A1", "A2"]
    assert sorted(works["matched_author_id"].unique()) == ["A1", "A2"]


class RecordingWorksClient:
    def iter_works_for_author(self, author_id: str):
        yield {
            "id": f"W-{author_id}",
            "title": f"Work for {author_id}",
            "publication_year": 2024,
            "cited_by_count": 1,
            "primary_location": {},
            "open_access": {},
            "authorships": [],
        }
