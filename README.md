# AYS Bibliometrics

Production-oriented command line tooling for annual bibliometric reporting for the
Andrew Young School of Policy Studies at Georgia State University.

The package computes two complementary measures:

- **Researcher Citation Footprint**: aggregate author-level citation profiles for
  reviewed AYS researchers.
- **Deduplicated School Impact**: unique publication impact after deduplicating
  OpenAlex works by Work ID.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configure

Copy `config.example.yaml` to `config.yaml` before running. At minimum, set `email`,
`openalex.polite_pool_email`, and, if your OpenAlex access requires it,
`openalex.api_key`. `config.yaml` is ignored by git because it may contain local
credentials.

## Pipeline

```bash
ays-bibliometrics build-roster
ays-bibliometrics match-authors
```

Review `output/site_matches.xlsx`, set `include` to `TRUE` only for approved
author rows, then continue. `output/all_matches.xlsx` contains the full
candidate list for auditing.

```bash
ays-bibliometrics download-works
ays-bibliometrics compute-metrics
ays-bibliometrics generate-report
```

Or, after matches have been reviewed:

```bash
ays-bibliometrics run-all
```

## Roster Providers

`build-roster` supports interchangeable providers:

- `ays_website`: discovers profile pages from the AYS profile directory and uses
  robust metadata extraction rather than a single brittle CSS selector.
- `csv`: loads an existing roster CSV.
- `manual`: loads manually configured people from `config.yaml`.
- `openalex_institution`: bootstraps likely researchers from OpenAlex institution
  author search.

## Outputs

Default outputs are written under `output/`:

- `roster.csv`
- `all_matches.xlsx`
- `site_matches.xlsx`
- `approved_authors.csv`
- `works.parquet`
- `works_authorships.parquet`
- `metrics/*.csv`
- `ays_bibliometrics_report.xlsx`
- `figures/*.png`
- `run.log`
