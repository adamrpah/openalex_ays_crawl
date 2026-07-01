from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import AppConfig
from .openalex import OpenAlexClient
from .util import clean_person_name, clean_url, first_nonempty, normalize_whitespace

logger = logging.getLogger(__name__)


@dataclass
class Person:
    name: str
    title: str = ""
    department: str = ""
    research_center: str = ""
    email: str = ""
    profile_url: str = ""
    source: str = ""
    notes: str = ""


class RosterProvider(ABC):
    @abstractmethod
    def build(self) -> pd.DataFrame:
        raise NotImplementedError


class CSVProvider(RosterProvider):
    def __init__(self, path) -> None:
        self.path = path

    def build(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        return normalize_roster(df, source="csv")


class ManualProvider(RosterProvider):
    def __init__(self, people: list[dict[str, Any]]) -> None:
        self.people = people

    def build(self) -> pd.DataFrame:
        return normalize_roster(pd.DataFrame(self.people), source="manual")


class OpenAlexInstitutionProvider(RosterProvider):
    def __init__(self, client: OpenAlexClient, institution_id: str) -> None:
        self.client = client
        self.institution_id = institution_id

    def build(self) -> pd.DataFrame:
        rows = []
        for author in self.client.iter_institution_authors(self.institution_id):
            rows.append(
                Person(
                    name=author.get("display_name", ""),
                    title="",
                    department="",
                    research_center="",
                    email="",
                    profile_url="",
                    source="openalex_institution",
                    notes=f"openalex_author_id={author.get('id', '')}",
                )
            )
        return normalize_roster(pd.DataFrame([asdict(row) for row in rows]), source="openalex_institution")


class AYSWebsiteProvider(RosterProvider):
    def __init__(self, website_url: str, departments: list[str], centers: list[str]) -> None:
        self.website_url = website_url
        self.departments = departments
        self.centers = centers
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ays-bibliometrics/0.1 roster discovery"})

    def build(self) -> pd.DataFrame:
        profile_urls = self.discover_profile_urls()
        rows: list[Person] = []
        for url in profile_urls:
            try:
                rows.append(self.parse_profile(url))
            except Exception as exc:  # noqa: BLE001
                logger.exception("roster_profile_parse_failed", extra={"_profile_url": url})
                rows.append(Person(name="", profile_url=url, source="ays_website", notes=str(exc)))
        return normalize_roster(pd.DataFrame([asdict(row) for row in rows]), source="ays_website")

    def fetch(self, url: str) -> BeautifulSoup:
        response = self.session.get(url, timeout=45)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def discover_profile_urls(self) -> list[str]:
        soup = self.fetch(self.website_url)
        urls: set[str] = set()
        index_urls = {clean_url(self.website_url)}
        for anchor in soup.find_all("a", href=True):
            href = urljoin(self.website_url, anchor["href"])
            cleaned = clean_url(href)
            if self._looks_like_profile_url(cleaned):
                urls.add(cleaned)
            elif self._looks_like_index_url(cleaned):
                index_urls.add(cleaned)
        for index_url in sorted(index_urls - {clean_url(self.website_url)}):
            try:
                page_soup = self.fetch(index_url)
            except requests.RequestException:
                logger.exception("roster_index_fetch_failed", extra={"_profile_url": index_url})
                continue
            for anchor in page_soup.find_all("a", href=True):
                cleaned = clean_url(urljoin(index_url, anchor["href"]))
                if self._looks_like_profile_url(cleaned):
                    urls.add(cleaned)
        if clean_url(self.website_url) in urls:
            urls.remove(clean_url(self.website_url))
        logger.info("roster_discovered_profiles", extra={"_count": len(urls)})
        return sorted(urls)

    def _looks_like_profile_url(self, url: str) -> bool:
        if "aysps.gsu.edu/profile/" not in url:
            return False
        tail = url.split("/profile/", 1)[-1].strip("/")
        return bool(tail) and not tail.startswith(("page/", "category/"))

    def _looks_like_index_url(self, url: str) -> bool:
        if "aysps.gsu.edu/profile/" not in url:
            return False
        tail = url.split("/profile/", 1)[-1].strip("/")
        return tail.startswith("page/")

    def parse_profile(self, url: str) -> Person:
        soup = self.fetch(url)
        profile_root = self._profile_root(soup)
        page_text = normalize_whitespace(soup.get_text(" "))
        name = first_nonempty(
            [
                profile_root.find("h1").get_text(" ", strip=True)
                if profile_root and profile_root.find("h1")
                else "",
                soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "",
                self._json_ld_name(profile_root or soup),
                self._meta(soup, "og:title"),
                self._name_from_url(url),
            ]
        )
        name = clean_person_name(name)
        email = self._extract_email(profile_root or soup, page_text)
        department = self._extract_department(profile_root or soup)
        center = self._extract_center(profile_root or soup)
        title = self._extract_title(profile_root or soup, name or "")
        return Person(
            name=name,
            title=title,
            department=department,
            research_center=center,
            email=email,
            profile_url=url,
            source="ays_website",
        )

    def _profile_root(self, soup: BeautifulSoup):
        return (
            soup.find("div", class_=re.compile(r"\bcontent-sidebar-wrap\b"))
            or soup.find("main", id="genesis-content")
            or soup.find("article", class_=re.compile(r"\btype-profile\b"))
            or soup
        )

    def _meta(self, soup: BeautifulSoup, property_name: str) -> str:
        tag = soup.find("meta", attrs={"property": property_name}) or soup.find(
            "meta", attrs={"name": property_name}
        )
        return normalize_whitespace(tag.get("content", "")) if tag else ""

    def _json_ld_name(self, soup: BeautifulSoup) -> str:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            match = re.search(r'"name"\s*:\s*"([^"]+)"', script.string)
            if match:
                return match.group(1)
        return ""

    def _name_from_url(self, url: str) -> str:
        slug = url.rstrip("/").split("/")[-1]
        return " ".join(part.capitalize() for part in slug.split("-"))

    def _extract_email(self, soup: BeautifulSoup, text: str) -> str:
        mailto = soup.find("a", href=re.compile(r"^mailto:", re.I))
        if mailto:
            return mailto["href"].split(":", 1)[1].strip()
        match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)
        return match.group(0) if match else ""

    def _find_known_phrase(self, text: str, phrases: list[str]) -> str:
        folded = text.lower()
        for phrase in phrases:
            if phrase.lower() in folded:
                return phrase
        return ""

    def _extract_department(self, root) -> str:
        department = self._find_department_alias(self._profile_taxonomy_texts(root))
        if department:
            return department
        return self._find_department_alias(self._profile_affiliation_texts(root))

    def _extract_center(self, root) -> str:
        texts = self._profile_taxonomy_texts(root) + self._profile_affiliation_texts(root)
        for text in texts:
            center = self._find_known_phrase(text, self.centers)
            if center:
                return center
        return ""

    def _profile_taxonomy_texts(self, root) -> list[str]:
        texts: list[str] = []
        for anchor in root.find_all("a"):
            href = anchor.get("href", "")
            text = normalize_whitespace(anchor.get_text(" "))
            if text and self._looks_profile_taxonomy(text, href):
                texts.append(text)
            if href and any(marker in href for marker in ["/category/department", "/department/"]):
                texts.append(href.replace("-", " ").replace("/", " "))
        for tag in [root, *root.find_all(True)]:
            class_text = " ".join(tag.get("class", []))
            if class_text and ("category-department" in class_text or " department-" in f" {class_text}"):
                texts.append(class_text.replace("-", " "))
        return texts

    def _profile_affiliation_texts(self, root) -> list[str]:
        texts: list[str] = []
        for selector in ["aside", ".sidebar-primary"]:
            for tag in root.select(selector):
                text = normalize_whitespace(tag.get_text(" "))
                if text and len(text) < 1000:
                    texts.append(text)
        for tag in root.find_all(["p", "h2", "h3", "li", "div"], limit=80):
            text = normalize_whitespace(tag.get_text(" "))
            if text and len(text) < 300 and self._looks_like_affiliation_line(text):
                texts.append(text)
        return texts

    def _looks_like_affiliation_line(self, text: str) -> bool:
        folded = text.lower()
        affiliation_markers = (
            "department",
            "dean's office",
            "school of",
            "institute",
            "center",
            "professor",
            "lecturer",
            "chair",
            "director",
        )
        return any(marker in folded for marker in affiliation_markers)

    def _looks_profile_taxonomy(self, text: str, href: str) -> bool:
        folded_text = text.lower()
        folded_href = href.lower()
        return (
            folded_text.startswith("department of ")
            or "/category/department" in folded_href
            or "/department/" in folded_href
        )

    def _find_department_alias(self, texts: list[str]) -> str:
        alias_map = self._department_aliases()
        for text in texts:
            folded = text.lower().replace("&", "and")
            for alias, canonical in alias_map:
                if re.search(rf"\b{re.escape(alias)}\b", folded):
                    return canonical
        return ""

    def _department_aliases(self) -> list[tuple[str, str]]:
        aliases: list[tuple[str, str]] = []
        for department in self.departments:
            folded = department.lower().replace("&", "and")
            aliases.append((folded, department))
            aliases.append((f"department of {folded}", department))
        aliases.extend(
            [
                ("criminal justice and criminology", "Criminal Justice and Criminology"),
                ("department of criminal justice and criminology", "Criminal Justice and Criminology"),
                ("cjc", "Criminal Justice and Criminology"),
                ("economics", "Economics"),
                ("department of economics", "Economics"),
                ("public management and policy", "Public Management and Policy"),
                ("department of public management and policy", "Public Management and Policy"),
                ("pmap", "Public Management and Policy"),
                ("social work", "Social Work"),
                ("school of social work", "Social Work"),
                ("urban studies institute", "Urban Studies Institute"),
                ("urban studies", "Urban Studies Institute"),
            ]
        )
        seen: set[tuple[str, str]] = set()
        unique = []
        for alias, canonical in aliases:
            key = (alias, canonical)
            if key not in seen:
                seen.add(key)
                unique.append(key)
        return sorted(unique, key=lambda item: len(item[0]), reverse=True)

    def _extract_title(self, soup: BeautifulSoup, name: str) -> str:
        candidates = []
        sidebar = soup.find("aside", class_=re.compile(r"\bsidebar-primary\b")) or soup.find("aside")
        if sidebar:
            sidebar_text = normalize_whitespace(sidebar.get_text(" "))
            match = re.search(
                rf"{re.escape(name)}\s+(.+?)(?:\s+Email:|\s+Curriculum Vitae|\s+Location|\s+[A-Z][\w\s]+@)",
                sidebar_text,
            )
            if match:
                affiliation_line = normalize_whitespace(match.group(1))
                title = re.split(r"\s{2,}|,?\s+Department of |,?\s+School of |,?\s+Dean's Office", affiliation_line)[0]
                if title and title.lower() != name.lower():
                    return title
        for selector in ["h2", "h3", "p", "li", "div"]:
            for tag in soup.find_all(selector, limit=30):
                text = normalize_whitespace(tag.get_text(" "))
                if text and text != name and len(text) < 180 and not self._looks_like_taxonomy_text(text):
                    candidates.append(text)
        title_words = ("professor", "lecturer", "dean", "chair", "director", "faculty", "instructor")
        for candidate in candidates:
            if any(word in candidate.lower() for word in title_words):
                return candidate
        return ""

    def _looks_like_taxonomy_text(self, text: str) -> bool:
        folded = text.lower()
        return folded.startswith("filed under:") or " tagged with:" in folded


def normalize_roster(df: pd.DataFrame, source: str) -> pd.DataFrame:
    columns = ["name", "title", "department", "research_center", "email", "profile_url", "source", "notes"]
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    df = df[columns].copy()
    for column in columns:
        df[column] = df[column].fillna("").map(lambda value: normalize_whitespace(str(value)))
    df["name"] = df["name"].map(clean_person_name)
    df.loc[df["source"].eq(""), "source"] = source
    df = df[df["name"].ne("")].drop_duplicates(subset=["name", "email", "profile_url"]).reset_index(drop=True)
    return df


def get_roster_provider(config: AppConfig, client: OpenAlexClient | None = None) -> RosterProvider:
    provider = config.roster.provider
    if provider == "ays_website":
        return AYSWebsiteProvider(config.roster.website_url, config.departments, config.centers)
    if provider == "csv":
        return CSVProvider(config.roster.input_csv)
    if provider == "manual":
        return ManualProvider(config.roster.manual_people)
    if provider == "openalex_institution":
        if client is None:
            raise ValueError("OpenAlex client is required for openalex_institution provider")
        return OpenAlexInstitutionProvider(client, config.roster.openalex_institution_id)
    raise ValueError(f"Unknown roster provider: {provider}")
