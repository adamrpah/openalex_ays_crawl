from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_metrics(metrics: dict[str, pd.DataFrame], metrics_dir: Path) -> None:
    metrics_dir.mkdir(parents=True, exist_ok=True)
    for name, df in metrics.items():
        df.to_csv(metrics_dir / f"{name}.csv", index=False)


def write_excel_report(metrics: dict[str, pd.DataFrame], works: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_map = {
        "Summary": metrics.get("publication_metrics", pd.DataFrame()),
        "Faculty": metrics.get("researcher_metrics", pd.DataFrame()),
        "Departments": metrics.get("department_summaries", pd.DataFrame()),
        "Centers": metrics.get("center_summaries", pd.DataFrame()),
        "Works": works,
        "Top Papers": metrics.get("top_papers", pd.DataFrame()),
        "Top Faculty": metrics.get("top_faculty", pd.DataFrame()),
        "Yearly Trends": metrics.get("year_summaries", pd.DataFrame()),
        "Top Journals": metrics.get("top_journals", pd.DataFrame()),
    }
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheet_map.items():
            safe_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
            worksheet = writer.sheets[safe_name]
            worksheet.freeze_panes = "A2"
            for column_cells in worksheet.columns:
                width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 60)
                worksheet.column_dimensions[column_cells[0].column_letter].width = width

