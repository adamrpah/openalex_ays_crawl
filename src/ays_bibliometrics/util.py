from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


def normalize_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", normalize_whitespace(value)).encode("ascii", "ignore")
    return text.decode("ascii").lower()


def clean_person_name(value: str | None) -> str:
    text = normalize_whitespace(value)
    if not text:
        return ""
    text = re.split(r"\s+\|\s+", text, maxsplit=1)[0]
    degree_pattern = r"(?:ph\.?d\.?|m\.?d\.?|mph|m\.?p\.?h\.?|m\.?s\.?w\.?|mba|m\.?b\.?a\.?)"
    text = re.sub(rf",?\s+{degree_pattern}\b\.?$", "", text, flags=re.IGNORECASE)
    return normalize_whitespace(text)


def cache_key(url: str, params: dict[str, Any] | None = None) -> str:
    parts = [url]
    if params:
        parts.extend(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def clean_url(url: str) -> str:
    split = urlsplit(url)
    return urlunsplit((split.scheme, split.netloc, split.path.rstrip("/") + "/", "", ""))


def first_nonempty(values: Iterable[Any]) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
