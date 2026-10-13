"""Claude API로 관련성 판정 + 소분류 태깅 + Lab score + 한 줄 요약.

환경변수 ANTHROPIC_API_KEY 필요.
"""
from __future__ import annotations

import json

import anthropic

from .config import Config

TOOL = {
    "name": "record_classifications",
    "description": "Record the classification result for every paper in the batch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "relevant": {"type": "boolean", "description": "Is the paper genuinely about the board topic?"},
                        "categories": {"type": "array", "items": {"type": "string"}},
                        "lab_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "tldr": {"type": "string", "description": "One-sentence takeaway."},
                    },
                    "required": ["id", "relevant", "categories", "lab_score", "tldr"],
                },
            }
        },
        "required": ["results"],
    },
}


def _system_prompt(cfg: Config) -> str:
    cats = "\n".join(f"- {c['id']}: {c['label']} — {c.get('description', '')}" for c in cfg.categories)
    return f"""You curate a literature briefing board for a research lab.

BOARD TOPIC: {cfg.board['title']}

LAB INTERESTS (use for lab_score):
{cfg.lab_profile}

SUB-CATEGORIES (assign every one that clearly applies; zero is allowed; use ids only):
{cats}

For each paper decide:
1. relevant — true only if the paper's main contribution is about the board topic.
   Keyword hits on unrelated work (e.g. aqueous dye degradation only, VOC sensing, combustion) are NOT relevant.
2. categories — list of category ids from above (only if relevant).
3. lab_score — 0-100, how useful this paper is for the LAB INTERESTS
   (90+: directly on our system/problem, 70+: strongly related, 40-70: same field, <40: peripheral).
4. tldr — one sentence in {cfg.board.get('summary_language', 'English')} stating what was done and the key finding.
   Keep chemical formulas and numbers as written.

Return results for ALL papers via the record_classifications tool."""


class Classifier:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = anthropic.Anthropic(max_retries=5)
        self.model = cfg.pipeline.get("model", "claude-haiku-5-5")
        self.system = _system_prompt(cfg)

    def classify(self, papers: list[dict]) -> dict[str, dict]:
        payload = [
            {"id": p["id"], "title": p["title"], "journal": p.get("journal"),
             "type": p.get("type"), "abstract": (p.get("abstract") or "")[:2500]}
            for p in papers
        ]
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            # 시스템 프롬프트는 매 호출 동일 → 프롬프트 캐싱으로 비용 절감
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": TOOL["name"]},
            messages=[{"role": "user", "content": "Classify these papers:\n" + json.dumps(payload, ensure_ascii=False)}],
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        out: dict[str, dict] = {}
        for r in block.input.get("results", []):
            cats = [c for c in r.get("categories", []) if c in self.cfg.category_ids]
            out[r["id"]] = {
                "relevant": bool(r.get("relevant")),
                "categories": cats if r.get("relevant") else [],
                "lab_score": max(0, min(100, int(r.get("lab_score", 0)))),
                "tldr": r.get("tldr", ""),
                "model": self.model,
            }
        return out

    def suggest_categories(self, titles: list[str], n: int = 12) -> str:
        """백필 결과 제목들을 보고 소분류 체계 초안 제안 (YAML 텍스트)."""
        msg = self.client.messages.create(
            model=self.cfg.pipeline.get("suggest_model", "claude-sonnet-5-5"),
            max_tokens=3000,
            messages=[{"role": "user", "content": (
                f"Board topic: {self.cfg.board['title']}\nLab interests:\n{self.cfg.lab_profile}\n\n"
                f"Below are {len(titles)} paper titles collected for this board. Propose about {n} "
                "sub-categories that a researcher would use to browse them (multi-label, mixing material "
                "families, target pollutants/reactions, mechanisms and application aspects as fits the topic). "
                "Output ONLY a YAML list in the format:\n"
                "- id: short_snake_id\n  label: \"Display label\"\n  description: \"one sentence rule for assignment\"\n\n"
                + "\n".join(f"- {t}" for t in titles)
            )}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
