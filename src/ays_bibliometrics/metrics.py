from __future__ import annotations

import pandas as pd


def h_index(citations: list[int]) -> int:
    sorted_citations = sorted((int(c or 0) for c in citations), reverse=True)
    return sum(c >= i for i, c in enumerate(sorted_citations, start=1))


def i10_index(citations: list[int]) -> int:
    return sum(int(c or 0) >= 10 for c in citations)


def researcher_metrics(works: pd.DataFrame, authorships: pd.DataFrame) -> pd.DataFrame:
    if works.empty or authorships.empty:
        return pd.DataFrame()
    joined = authorships.merge(
        works[["work_id", "cited_by_count", "publication_year"]], on="work_id", how="left"
    )
    rows = []
    for person, group in joined.groupby("matched_person_name"):
        citations = (
            group.drop_duplicates("work_id")["cited_by_count"].fillna(0).astype(int).tolist()
        )
        years = group["publication_year"].dropna()
        span = max(int(years.max()) - int(years.min()) + 1, 1) if not years.empty else 1
        publications = group["work_id"].nunique()
        rows.append(
            {
                "person_name": person,
                "author_id": "; ".join(unique_nonempty_values(group, "matched_author_id")),
                "publications": publications,
                "citations": sum(citations),
                "h_index": h_index(citations),
                "i10_index": i10_index(citations),
                "citations_per_year": round(sum(citations) / span, 2),
                "publications_per_year": round(publications / span, 2),
                "department": first_nonempty_value(group, "person_department"),
                "research_center": first_nonempty_value(group, "person_research_center"),
            }
        )
    return pd.DataFrame(rows).sort_values(["citations", "publications"], ascending=False)


def first_nonempty_value(df: pd.DataFrame, column: str) -> str:
    values = unique_nonempty_values(df, column)
    return values[0] if values else ""


def unique_nonempty_values(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values: list[str] = []
    for value in df[column]:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text and text not in values:
            values.append(text)
    return values


def publication_metrics(deduped: pd.DataFrame) -> pd.DataFrame:
    total_publications = len(deduped)
    total_citations = int(deduped["cited_by_count"].fillna(0).sum()) if total_publications else 0
    oa_percentage = float(deduped["is_oa"].fillna(False).mean() * 100) if total_publications else 0.0
    return pd.DataFrame(
        [
            {
                "total_unique_publications": total_publications,
                "total_unique_citations": total_citations,
                "citations_per_publication": round(total_citations / total_publications, 2) if total_publications else 0,
                "oa_percentage": round(oa_percentage, 2),
                "international_collaboration_percentage": round(
                    float(deduped["international_collaboration"].fillna(False).mean() * 100), 2
                )
                if total_publications
                else 0,
            }
        ]
    )


def department_summaries(researchers: pd.DataFrame) -> pd.DataFrame:
    if researchers.empty:
        return pd.DataFrame()
    return (
        researchers.groupby("department", dropna=False)
        .agg(
            faculty=("person_name", "nunique"),
            publications=("publications", "sum"),
            citations=("citations", "sum"),
            median_h_index=("h_index", "median"),
        )
        .reset_index()
        .sort_values("citations", ascending=False)
    )


def center_summaries(researchers: pd.DataFrame) -> pd.DataFrame:
    if researchers.empty:
        return pd.DataFrame()
    return (
        researchers.groupby("research_center", dropna=False)
        .agg(
            faculty=("person_name", "nunique"),
            publications=("publications", "sum"),
            citations=("citations", "sum"),
            median_h_index=("h_index", "median"),
        )
        .reset_index()
        .sort_values("citations", ascending=False)
    )


def year_summaries(deduped: pd.DataFrame) -> pd.DataFrame:
    if deduped.empty:
        return pd.DataFrame()
    return (
        deduped.groupby("publication_year", dropna=False)
        .agg(publications=("work_id", "nunique"), citations=("cited_by_count", "sum"), oa_publications=("is_oa", "sum"))
        .reset_index()
        .sort_values("publication_year")
    )


def top_journals(deduped: pd.DataFrame, limit: int = 50) -> pd.DataFrame:
    if deduped.empty:
        return pd.DataFrame()
    return (
        deduped.groupby("journal", dropna=False)
        .agg(publications=("work_id", "nunique"), citations=("cited_by_count", "sum"))
        .reset_index()
        .sort_values(["publications", "citations"], ascending=False)
        .head(limit)
    )


def top_papers(deduped: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    if deduped.empty:
        return pd.DataFrame()
    columns = [
        "title",
        "publication_year",
        "journal",
        "cited_by_count",
        "doi",
        "work_id",
        "ays_matched_authors",
        "departments",
        "research_centers",
        "is_oa",
    ]
    return deduped.sort_values("cited_by_count", ascending=False)[columns].head(limit)


def top_faculty(researchers: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    if researchers.empty:
        return pd.DataFrame()
    return researchers.sort_values(["citations", "h_index"], ascending=False).head(limit)
