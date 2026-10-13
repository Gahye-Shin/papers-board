"""config.yaml 로딩과 저널 → 티어 매칭."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def norm_name(name: str | None) -> str:
    """저널명 정규화: 소문자, &→and, 구두점·'the' 제거."""
    if not name:
        return ""
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\bthe\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self.raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.board = self.raw["board"]
        self.queries: list[str] = self.raw["queries"]
        self.lab_profile: str = self.raw.get("lab_profile", "").strip()
        self.categories: list[dict] = self.raw["categories"]
        self.category_ids = {c["id"] for c in self.categories}
        self.tiers: list[dict] = self.raw.get("journal_tiers", [])
        self.only_listed: bool = bool(self.raw.get("only_listed_journals", False))
        self.pipeline: dict = self.raw.get("pipeline", {})

        # 저널 이름/ISSN → tier id 사전
        self._by_name: dict[str, str] = {}
        self._by_issn: dict[str, str] = {}
        for tier in self.tiers:
            for j in tier.get("journals", []):
                if isinstance(j, str):
                    j = {"name": j}
                for n in [j["name"], *j.get("aliases", [])]:
                    self._by_name[norm_name(n)] = tier["id"]
                for issn in j.get("issn", []) if isinstance(j.get("issn"), list) else [j.get("issn")]:
                    if issn:
                        self._by_issn[issn.strip()] = tier["id"]

    @property
    def journal_count(self) -> int:
        return sum(len(t.get("journals", [])) for t in self.tiers)

    def tier_of(self, journal_name: str | None, issns: list[str] | None) -> str | None:
        for issn in issns or []:
            if issn in self._by_issn:
                return self._by_issn[issn]
        return self._by_name.get(norm_name(journal_name))

    def public_meta(self) -> dict:
        """웹 보드에 넘길 설정 요약."""
        return {
            "title": self.board.get("title", "Papers Board"),
            "subtitle": self.board.get("subtitle", ""),
            "start_year": self.board.get("start_year"),
            "journal_count": self.journal_count,
            "categories": [{"id": c["id"], "label": c["label"]} for c in self.categories],
            "tiers": [{"id": t["id"], "label": t["label"]} for t in self.tiers],
            "highlight_score": self.pipeline.get("min_lab_score_to_highlight", 70),
        }
