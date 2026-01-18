#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from tranco import Tranco

def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch a Tranco top-N list and write it as newline-delimited domains.")
    ap.add_argument("--top", type=int, default=10000)
    ap.add_argument("--date", type=str, default=None, help="YYYY-MM-DD snapshot date (recommended)")
    ap.add_argument("--cache-dir", type=str, default=".tranco_cache")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    t = Tranco(cache=True, cache_dir=args.cache_dir)
    lst = t.list(date=args.date) if args.date else t.list()
    domains = lst.top(args.top)

    Path(args.out).write_text("\n".join(domains) + "\n", encoding="utf-8")
    print(f"Wrote {len(domains):,} domains to {args.out}")

if __name__ == "__main__":
    main()
