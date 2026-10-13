"""OpenAlex에서 후보 논문 수집.

API 키(무료)는 https://openalex.org/settings/api 에서 발급 → 환경변수 OPENALEX_API_KEY
키 없이도 동작하지만 하루 사용량이 매우 작습니다.
"""
from __future__ import annotations

import os
import time
from datetime import date
from typing import Iterator

import requests

API = "https://api.openalex.org/works"
SELECT = ",".join([
    "id", "doi", "title", "publication_date", "publication_year", "type",
    "primary_location", "authorships", "cited_by_count", "abstract_inverted_index",
])

_session = requests.Session()


def _params(extra: dict) -> dict:
    p = dict(extra)
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        p["api_key"] = key
    return p


def _get(params: dict) -> dict:
    for attempt in range(6):
        r = _session.get(API, params=_params(params), timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"OpenAlex {r.status_code}: {r.text[:300]}")
    raise RuntimeError("OpenAlex: 재시도 한도 초과")


def abstract_from_index(inv: dict | None) -> str:
    if not inv:
        return ""
    pos: dict[int, str] = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def simplify(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    authors = [
        (a.get("author") or {}).get("display_name")
        for a in (w.get("authorships") or [])
    ]
    authors = [a for a in authors if a]
    return {
        "id": w["id"].rsplit("/", 1)[-1],              # W123...
        "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        "title": w.get("title") or "",
        "date": w.get("publication_date"),
        "year": w.get("publication_year"),
        "type": w.get("type"),
        "journal": src.get("display_name"),
        "issn": src.get("issn") or [],
        "authors": authors[:12] + (["…"] if len(authors) > 12 else []),
        "citations": w.get("cited_by_count") or 0,
        "abstract": abstract_from_index(w.get("abstract_inverted_index")),
        "url": loc.get("landing_page_url") or (f"https://doi.org/{w['doi']}" if w.get("doi") else w["id"]),
    }


def search_works(query: str, from_date: date, to_date: date | None = None,
                 types: list[str] | None = None, limit: int | None = None) -> Iterator[dict]:
    filters = [f"title_and_abstract.search:{query}", f"from_publication_date:{from_date.isoformat()}"]
    if to_date:
        filters.append(f"to_publication_date:{to_date.isoformat()}")
    if types:
        filters.append("type:" + "|".join(types))
    cursor, n = "*", 0
    while cursor:
        data = _get({"filter": ",".join(filters), "per-page": 200, "cursor": cursor, "select": SELECT})
        for w in data.get("results", []):
            yield simplify(w)
            n += 1
            if limit and n >= limit:
                return
        cursor = data.get("meta", {}).get("next_cursor")


def refresh_citations(ids: list[str]) -> dict[str, int]:
    """ID 50개씩 묶어 인용수만 갱신."""
    out: dict[str, int] = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        data = _get({"filter": "openalex_id:" + "|".join(chunk), "per-page": 50, "select": "id,cited_by_count"})
        for w in data.get("results", []):
            out[w["id"].rsplit("/", 1)[-1]] = w.get("cited_by_count") or 0
    return out
