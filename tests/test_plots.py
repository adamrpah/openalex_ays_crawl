from __future__ import annotations

import pandas as pd

from ays_bibliometrics.plots import generate_figures, year_labels


def test_year_labels_handles_missing_years() -> None:
    assert year_labels(pd.Series([2024.0, None])) == ["2024", "Unknown"]


def test_generate_figures_handles_missing_publication_year(tmp_path) -> None:
    metrics = {
        "year_summaries": pd.DataFrame(
            [
                {
                    "publication_year": 2024.0,
                    "publications": 2,
                    "citations": 10,
                    "oa_publications": 1,
                },
                {
                    "publication_year": None,
                    "publications": 1,
                    "citations": 4,
                    "oa_publications": 0,
                },
            ]
        ),
        "top_faculty": pd.DataFrame(),
    }

    generate_figures(metrics, tmp_path)

    assert (tmp_path / "publications_by_year.png").exists()
    assert (tmp_path / "citations_by_year.png").exists()
