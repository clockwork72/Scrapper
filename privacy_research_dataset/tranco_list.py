from __future__ import annotations

from dataclasses import dataclass

@dataclass
class RankedSite:
    rank: int
    domain: str

def get_tranco_sites(top_n: int, date: str | None, cache_dir: str) -> list[RankedSite]:
    """Returns a reproducible Tranco list snapshot (top N) using the official `tranco` Python package."""
    try:
        from tranco import Tranco
    except Exception as e:
        raise RuntimeError("Missing dependency `tranco`. Install with `pip install tranco`.") from e

    t = Tranco(cache=True, cache_dir=cache_dir)
    lst = t.list(date=date) if date else t.list()

    domains = lst.top(top_n)
    return [RankedSite(rank=i, domain=d) for i, d in enumerate(domains, start=1)]
