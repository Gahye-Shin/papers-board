"""논문 누적 저장소 (data/papers.json). OpenAlex ID가 고유 키 → 매일 돌려도 중복 없음."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

DATA = ROOT / "data"
PAPERS = DATA / "papers.json"
STATE = DATA / "state.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self):
        DATA.mkdir(exist_ok=True)
        self.papers: dict[str, dict] = json.loads(PAPERS.read_text("utf-8")) if PAPERS.exists() else {}
        self.state: dict = json.loads(STATE.read_text("utf-8")) if STATE.exists() else {}

    def add(self, paper: dict, mode: str = "daily") -> bool:
        """새 논문이면 추가하고 True. 기존 논문은 인용수 등 메타데이터만 갱신."""
        pid = paper["id"]
        if pid in self.papers:
            old = self.papers[pid]
            for k in ("citations", "journal", "issn", "url", "date", "year"):
                if paper.get(k):
                    old[k] = paper[k]
            if not old.get("abstract") and paper.get("abstract"):
                old["abstract"] = paper["abstract"]
                old.pop("classification", None)   # 초록이 새로 생기면 재분류
            return False
        paper["first_seen"] = now_iso()
        paper["added_by"] = mode           # backfill 분은 NEW 표시에서 제외
        self.papers[pid] = paper
        return True

    def unclassified(self) -> list[dict]:
        return [p for p in self.papers.values() if "classification" not in p]

    def save(self):
        PAPERS.write_text(json.dumps(self.papers, ensure_ascii=False, indent=0), "utf-8")
        STATE.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), "utf-8")
