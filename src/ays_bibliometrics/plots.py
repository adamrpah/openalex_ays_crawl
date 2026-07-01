from __future__ import annotations

import os
import tempfile
from pathlib import Path

cache_root = Path(tempfile.gettempdir()) / "ays_bibliometrics_matplotlib"
os.environ.setdefault("MPLCONFIGDIR", str(cache_root))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))

import matplotlib.pyplot as plt
import pandas as pd


def generate_figures(metrics: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    yearly = metrics.get("year_summaries", pd.DataFrame())
    if not yearly.empty:
        known_years = yearly[yearly["publication_year"].notna()].copy()
        if not known_years.empty:
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.plot(
                known_years["publication_year"].astype(int),
                known_years["publications"],
                marker="o",
                label="Publications",
            )
            ax.set_title("AYS Unique Publications by Year")
            ax.set_xlabel("Publication Year")
            ax.set_ylabel("Publications")
            ax.grid(True, alpha=0.3)
            ax.legend()
            fig.tight_layout()
            fig.savefig(output_dir / "publications_by_year.png", dpi=300)
            plt.close(fig)

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(year_labels(yearly["publication_year"]), yearly["citations"])
        ax.set_title("AYS Citations by Publication Year")
        ax.set_xlabel("Publication Year")
        ax.set_ylabel("Citations")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        fig.savefig(output_dir / "citations_by_year.png", dpi=300)
        plt.close(fig)

    faculty = metrics.get("top_faculty", pd.DataFrame()).head(20)
    if not faculty.empty:
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.barh(faculty["person_name"], faculty["citations"])
        ax.invert_yaxis()
        ax.set_title("Top Cited AYS Faculty")
        ax.set_xlabel("Citations")
        fig.tight_layout()
        fig.savefig(output_dir / "top_faculty_citations.png", dpi=300)
        plt.close(fig)


def year_labels(years: pd.Series) -> list[str]:
    labels: list[str] = []
    for year in years:
        if pd.isna(year):
            labels.append("Unknown")
        else:
            labels.append(str(int(year)))
    return labels
