"""Find which public job board a company uses.

For each seed company, try its likely slugs against every board API that needs
no auth, and keep the boards that return postings. This is how the company
list grows without hand-writing a scraper per company.

  python -m jobfinder discover seeds.txt            # print what was found
  python -m jobfinder discover seeds.txt --write    # merge into companies.yaml

Seed file: one company per line, optional slug hints after a pipe:
  Razorpay | razorpaysoftwareprivatelimited
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
import yaml

from . import enrich
from .pipeline import COMPANIES_PATH
from .sources import ADAPTERS, UA

BOARDS = ["greenhouse", "lever", "ashby", "smartrecruiters", "workable", "recruitee"]
_LIMITS = {"greenhouse": 12, "lever": 4, "ashby": 10, "smartrecruiters": 6,
           "workable": 2, "recruitee": 6}


def parse_seeds(path: str) -> list[tuple[str, list[str]]]:
    seeds = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, _, hints = (part.strip() for part in line.partition("|"))
        explicit = [h.strip() for h in hints.split(",") if h.strip()]
        base = re.sub(r"[^a-z0-9 ]", "", name.lower())
        guesses = [base.replace(" ", ""), base.replace(" ", "-")]
        slugs = list(dict.fromkeys(explicit + [g for g in guesses if len(g) >= 3]))
        seeds.append((name, slugs))
    return list({name.lower(): (name, slugs) for name, slugs in seeds}.values())


def india_count(raw: list[dict], board: str) -> int:
    if board == "smartrecruiters":   # already queried with country=in
        return len(raw)
    return sum(1 for r in raw if enrich.locate(r.get("location"))["scope"] == "india")


async def probe(client, sems, name: str, slugs: list[str]) -> dict | None:
    """Best board for one company, or None.

    A slug can belong to an unrelated company or a vendor test board, so a
    board only counts when it lists India jobs right now. Companies that miss
    stay in the seed file and are retried on the next discover run.
    """
    best = None
    for slug in slugs:
        async def try_board(board: str):
            async with sems[board]:
                try:
                    raw = await ADAPTERS[board](client, {"name": name, "slug": slug})
                except Exception:
                    return None
            if not raw:
                return None
            return {"name": name, "ats": board, "slug": slug,
                    "total": len(raw), "india": india_count(raw, board)}

        hits = [h for h in await asyncio.gather(*(try_board(b) for b in BOARDS)) if h]
        for hit in hits:
            if not hit["india"]:
                continue
            if best is None or (hit["india"], hit["total"]) > (best["india"], best["total"]):
                best = hit
        if best:
            break
    return best


async def discover(seed_path: str, write: bool = False) -> list[dict]:
    seeds = parse_seeds(seed_path)
    known = yaml.safe_load(COMPANIES_PATH.read_text(encoding="utf-8")) or {"companies": []}
    have = {c["name"].lower() for c in known["companies"]}
    todo = [s for s in seeds if s[0].lower() not in have]
    print(f"{len(seeds)} seeds, {len(todo)} not yet in companies.yaml")

    sems = {b: asyncio.Semaphore(n) for b, n in _LIMITS.items()}
    async with httpx.AsyncClient(
        follow_redirects=True, headers={"Accept": "application/json", "User-Agent": UA},
        limits=httpx.Limits(max_connections=40),
    ) as client:
        results = await asyncio.gather(*(probe(client, sems, *s) for s in todo))

    found = [r for r in results if r]
    missing = [s[0] for s, r in zip(todo, results) if not r]
    for r in sorted(found, key=lambda r: -r["india"]):
        print(f"  {r['name']:30} {r['ats']:16} {r['slug']:32} india={r['india']:4} total={r['total']}")
    print(f"\nFound {len(found)} boards; {sum(r['india'] for r in found)} India jobs listed right now.")
    print(f"No public board found for {len(missing)}: {', '.join(missing)}")

    if write and found:
        for r in found:
            known["companies"].append(
                {"name": r["name"], "ats": r["ats"], "slug": r["slug"], "enabled": True}
            )
        COMPANIES_PATH.write_text(
            yaml.safe_dump(known, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        print(f"Added {len(found)} companies to {COMPANIES_PATH.name}")
    return found
