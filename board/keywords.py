"""무료 분류기: config.yaml의 키워드 규칙으로 관련성·소분류·Lab score를 매깁니다 (API 불필요).

키워드 작성 규칙
  - 모두 소문자로 쓰면 대소문자 무시:  formaldehyde → Formaldehyde, FORMALDEHYDE 모두 매칭
  - 대문자가 섞이면 대소문자 구분:      HCHO, Au, NOx, TiO2  (→ "au"나 "nox"로 쓰면 오매칭 많음)
  - 끝에 * 를 붙이면 접두어 매칭:       photocataly* → photocatalyst, photocatalytic, photocatalysis
  - 화학식의 아래첨자(₂)는 일반 숫자(2)로 바꿔서 비교하므로 TiO2 로만 적으면 됩니다
"""
from __future__ import annotations

import re
from functools import lru_cache

from .config import Config

_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


@lru_cache(maxsize=4096)
def _pattern(kw: str) -> re.Pattern:
    kw = kw.strip().translate(_SUB)
    prefix = kw.endswith("*")
    core = re.escape(kw.rstrip("*")).replace(r"\ ", r"[\s\-]+")   # 공백 = 공백 또는 하이픈
    flags = 0 if any(c.isupper() for c in kw) else re.IGNORECASE
    tail = r"\w*" if prefix else r"(?![A-Za-z])"
    return re.compile(r"(?<![A-Za-z])" + core + tail, flags)


def hits(text: str, keywords: list[str] | None) -> list[str]:
    return [k for k in (keywords or []) if _pattern(k).search(text)]


class KeywordClassifier:
    model = "keywords"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        r = cfg.raw.get("relevance", {}) or {}
        self.must = r.get("must_have_any", [])
        self.context = r.get("context_any", [])
        self.exclude_title = r.get("exclude_if_in_title", [])
        self.exclude_unless_context = r.get("exclude_unless_context_in_title", [])
        self.lab = cfg.raw.get("lab_keywords", {}) or {}

    def classify_one(self, p: dict) -> dict:
        title = (p.get("title") or "").translate(_SUB)
        text = (title + " " + (p.get("abstract") or "")).translate(_SUB)

        relevant = bool(hits(text, self.must)) and (not self.context or bool(hits(text, self.context)))
        if relevant and hits(title, self.exclude_title):
            relevant = False
        if relevant and hits(text, self.exclude_unless_context) and not hits(title, self.context):
            relevant = False

        cats = [c["id"] for c in self.cfg.categories if hits(text, c.get("keywords"))] if relevant else []

        score = 0
        for kw, w in self.lab.items():
            if _pattern(str(kw)).search(text):
                score += int(w)
        return {
            "relevant": relevant,
            "categories": cats,
            "lab_score": max(0, min(100, score)),
            "tldr": "",
            "model": self.model,
        }

    def classify(self, papers: list[dict]) -> dict[str, dict]:
        return {p["id"]: self.classify_one(p) for p in papers}
