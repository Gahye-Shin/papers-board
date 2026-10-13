"""실행 진입점.

  python -m board.run backfill            # 최초 1회: start_year부터 전부 수집·분류
  python -m board.run daily               # 매일: 최근 N일 신규 논문 수집·분류
  python -m board.run refresh-citations   # 인용수 갱신 (workflow에서 주 1회)
  python -m board.run reclassify [--all]  # 소분류 바꾼 뒤 재분류
  python -m board.run suggest-categories  # 백필 결과로 소분류 체계 초안 제안
  python -m board.run build               # 웹 보드 데이터(site/data)만 재생성

공통 옵션: --limit N (검색어당 최대 N편, 테스트용)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone

from . import openalex
from .config import ROOT, Config
from .store import Store, now_iso

SITE_DATA = ROOT / "site" / "data"


def log(*a):
    print(*a, flush=True)


# ── 수집 ───────────────────────────────────────────────────
def collect(cfg: Config, store: Store, from_date: date, limit: int | None, mode: str) -> int:
    types = cfg.pipeline.get("include_types", ["article", "review"])
    new = 0
    for q in cfg.queries:
        log(f"[수집] {q}")
        n_q = 0
        for paper in openalex.search_works(q, from_date, types=types, limit=limit):
            paper["tier"] = cfg.tier_of(paper.get("journal"), paper.get("issn"))
            if cfg.only_listed and not paper["tier"]:
                continue
            n_q += 1
            new += store.add(paper, mode)
        log(f"       → {n_q}편 확인")
    log(f"[수집] 신규 후보 {new}편")
    return new


# ── 분류 ───────────────────────────────────────────────────
def classify_pending(cfg: Config, store: Store, papers: list[dict] | None = None):
    from .classify import Classifier  # anthropic 미설치 상태에서도 build는 돌도록 지연 import

    todo = papers if papers is not None else store.unclassified()
    if not todo:
        log("[분류] 대상 없음")
        return
    clf = Classifier(cfg)
    bs = int(cfg.pipeline.get("batch_size", 10))
    log(f"[분류] {len(todo)}편 · {clf.model} · 배치 {bs}")
    for i in range(0, len(todo), bs):
        batch = todo[i:i + bs]
        try:
            res = clf.classify(batch)
        except Exception as e:  # 한 배치 실패해도 다음 실행 때 다시 시도
            log(f"  ! 배치 {i // bs + 1} 실패: {e}")
            continue
        for p in batch:
            if p["id"] in res:
                store.papers[p["id"]]["classification"] = {**res[p["id"]], "at": now_iso()}
        if (i // bs) % 10 == 9:
            store.save()
        log(f"  {min(i + bs, len(todo))}/{len(todo)}")
    store.save()


# ── 웹 보드 데이터 생성 ────────────────────────────────────
def build(cfg: Config, store: Store):
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    rows = []
    relevant_total = 0
    for p in store.papers.values():
        c = p.get("classification")
        if not c or not c.get("relevant"):
            continue
        relevant_total += 1
        tier = cfg.tier_of(p.get("journal"), p.get("issn"))   # 설정 변경 반영
        if cfg.only_listed and not tier:
            continue
        rows.append({
            "id": p["id"], "doi": p.get("doi"), "title": p["title"], "date": p.get("date"),
            "year": p.get("year"), "type": p.get("type"), "journal": p.get("journal"),
            "tier": tier, "authors": p.get("authors", []), "citations": p.get("citations", 0),
            "abstract": p.get("abstract", ""), "url": p.get("url"),
            "categories": c.get("categories", []), "lab_score": c.get("lab_score", 0),
            "tldr": c.get("tldr", ""), "first_seen": p.get("first_seen"),
            "added_by": p.get("added_by", "daily"),
        })
    rows.sort(key=lambda r: (r["lab_score"], r["citations"]), reverse=True)
    meta = {
        **cfg.public_meta(),
        "updated": store.state.get("last_update") or now_iso(),
        "last_new_batch": store.state.get("last_new_batch"),
        "relevant_found": relevant_total,
        "candidates_screened": len(store.papers),
    }
    (SITE_DATA / "board.json").write_text(
        json.dumps({"meta": meta, "papers": rows}, ensure_ascii=False, separators=(",", ":")), "utf-8")
    log(f"[빌드] 보드 {len(rows)}편 (관련 {relevant_total} / 스크리닝 {len(store.papers)})")


# ── 명령 ───────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["backfill", "daily", "refresh-citations", "reclassify",
                                        "suggest-categories", "build"])
    ap.add_argument("--limit", type=int, default=None, help="검색어당 최대 편수 (테스트용)")
    ap.add_argument("--all", action="store_true", help="reclassify: 관련 없음 판정 논문까지 전부")
    args = ap.parse_args(argv)

    cfg, store = Config(), Store()
    started = now_iso()

    if args.command in ("backfill", "daily"):
        if args.command == "backfill":
            from_date = date(int(cfg.board.get("start_year", 2016)), 1, 1)
        else:
            days = int(cfg.pipeline.get("daily_lookback_days", 30))
            from_date = datetime.now(timezone.utc).date() - timedelta(days=days)
        new = collect(cfg, store, from_date, args.limit, args.command)
        store.save()
        classify_pending(cfg, store)
        store.state["last_update"] = started
        if new and args.command == "daily":
            store.state["last_new_batch"] = started
        store.state.setdefault("runs", []).append({"at": started, "mode": args.command, "new": new})
        store.state["runs"] = store.state["runs"][-60:]
        store.save()
        build(cfg, store)

    elif args.command == "refresh-citations":
        ids = list(store.papers)
        log(f"[인용수] {len(ids)}편 갱신")
        for pid, n in openalex.refresh_citations(ids).items():
            store.papers[pid]["citations"] = n
        store.save()
        build(cfg, store)

    elif args.command == "reclassify":
        todo = [p for p in store.papers.values()
                if args.all or (p.get("classification") or {}).get("relevant")]
        classify_pending(cfg, store, todo)
        build(cfg, store)

    elif args.command == "suggest-categories":
        from .classify import Classifier
        titles = [p["title"] for p in store.papers.values()
                  if (p.get("classification") or {}).get("relevant", True) and p.get("title")]
        if not titles:
            sys.exit("먼저 backfill을 실행하세요.")
        random.seed(0)
        sample = random.sample(titles, min(400, len(titles)))
        print(Classifier(cfg).suggest_categories(sample))

    elif args.command == "build":
        build(cfg, store)


if __name__ == "__main__":
    main()
