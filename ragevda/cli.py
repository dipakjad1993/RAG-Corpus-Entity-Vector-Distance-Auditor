"""Command-line interface for RAG-EVDA.

Usage
-----
  # generate a starter config
  python -m ragevda.cli init -o config.yaml

  # run from a config file (full audit)
  python -m ragevda.cli run -c config.yaml

  # quick run without a config file
  python -m ragevda.cli quick \
      --brand "Acme Software" \
      --topics "enterprise churn prediction" "SaaS pipeline analytics" \
      --competitors Salesforce HubSpot \
      --depth 30
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List

from . import __version__
from .config import RunConfig, DEFAULT_EMBEDDING_MODEL, DEFAULT_SPACY_MODEL
from .orchestrator import run
from .utils import get_logger

logger = get_logger("ragevda.cli")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ragevda",
        description="RAG Corpus Entity & Vector Distance Auditor (zero-cost).",
    )
    p.add_argument("--version", action="version", version=f"ragevda {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    # init
    pi = sub.add_parser("init", help="write an example config file")
    pi.add_argument("-o", "--out", default="config.yaml")

    # run
    pr = sub.add_parser("run", help="run audit from a config file")
    pr.add_argument("-c", "--config", required=True)

    # interactive
    pi2 = sub.add_parser(
        "interactive",
        help="type the 5 inputs at prompts, then run the audit",
    )

    # web
    pw = sub.add_parser("web", help="launch the local web UI (localhost)")
    pw.add_argument("--host", default="127.0.0.1")
    pw.add_argument("--port", type=int, default=8765)

    # quick
    pq = sub.add_parser("quick", help="run audit from CLI flags")
    pq.add_argument("--brand", required=True)
    pq.add_argument("--topics", required=True, nargs="+")
    pq.add_argument("--competitors", required=True, nargs="+")
    pq.add_argument("--depth", type=int, default=30)
    pq.add_argument("--locality", default=None)
    pq.add_argument("--harvester", default="duckduckgo",
                    choices=["duckduckgo", "searxng", "file"])
    pq.add_argument("--searxng-url", default=None)
    pq.add_argument("--prefer-searxng", dest="prefer_searxng",
                    action="store_true", default=False,
                    help="use SearXNG as primary live search when a URL is set")
    pq.add_argument("--corpus-dir", default=None)
    pq.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    pq.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    pq.add_argument("--output-dir", default="./ragevda_output")
    pq.add_argument("--no-reddit", action="store_true")
    pq.add_argument("--no-news", action="store_true")
    pq.add_argument("--auto-threshold", dest="auto_threshold",
                    action="store_true", default=True)
    pq.add_argument("--no-auto-threshold", dest="auto_threshold",
                    action="store_false")
    pq.add_argument("--high-relevance-threshold", dest="hrt", type=float, default=0.70)

    # history
    ph = sub.add_parser("history", help="show run-history trends for a brand")
    ph.add_argument("--brand", default=None)
    ph.add_argument("--jobs-dir", default="web_output/jobs")
    return p


def _example_config() -> dict:
    return {
        "target_brand": "Acme Software",
        "industry_topics": [
            "enterprise churn prediction",
            "SaaS pipeline analytics",
            "CRM automation",
        ],
        "competitor_entities": ["Salesforce", "HubSpot", "Zendesk"],
        "crawl_depth": 50,
        "locality": None,
        "harvester": "duckduckgo",
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "spacy_model": DEFAULT_SPACY_MODEL,
        "output_dir": "./ragevda_output",
        "include_reddit": True,
        "include_news": True,
    }


def main(argv: List[str] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger("ragevda").setLevel(logging.DEBUG)

    if args.command == "init":
        import os

        if os.path.exists(args.out):
            logger.error("refusing to overwrite existing file: %s", args.out)
            return 2
        with open(args.out, "w", encoding="utf-8") as fh:
            import yaml

            yaml.safe_dump(_example_config(), fh, sort_keys=False)
        logger.info("wrote example config -> %s", args.out)
        return 0

    if args.command == "run":
        cfg = RunConfig.load(args.config)
        run(cfg)
        return 0

    if args.command == "quick":
        cfg = RunConfig(
            target_brand=args.brand,
            industry_topics=args.topics,
            competitor_entities=args.competitors,
            crawl_depth=args.depth,
            locality=args.locality,
            harvester=args.harvester,
            searxng_base_url=args.searxng_url,
            corpus_dir=args.corpus_dir,
            embedding_model=args.embedding_model,
            spacy_model=args.spacy_model,
            output_dir=args.output_dir,
            include_reddit=not args.no_reddit,
            include_news=not args.no_news,
            auto_threshold=args.auto_threshold,
            high_relevance_threshold=args.hrt,
            prefer_searxng=args.prefer_searxng,
        )
        run(cfg)
        return 0

    if args.command == "history":
        from .tracking import load_runs, brands, runs_for_brand

        runs = load_runs(args.jobs_dir)
        if not runs:
            print("No runs found in", args.jobs_dir)
            return 0
        blist = brands(runs)
        brand = args.brand or blist[0]
        if brand not in blist:
            print("Available brands:", ", ".join(blist))
            return 2
        br = runs_for_brand(runs, brand)
        print(f"\nHistory for '{brand}' ({len(br)} runs)\n")
        print(f"{'when':<18}{'docs':>6}{'SoV%':>8}{'Inv%':>8}")
        for r in br:
            print(f"{r.generated_at.strftime('%Y-%m-%d %H:%M'):<18}"
                  f"{r.doc_count:>6}{r.composite_sov:>8}{r.rag_invisibility_index:>8}")
        return 0

    if args.command == "interactive":
        cfg = _prompt_inputs()
        run(cfg)
        return 0

    if args.command == "web":
        from .webapp import run_app

        logger.info("starting web UI at http://%s:%d/", args.host, args.port)
        run_app(args.host, args.port)
        return 0

    return 1


def _prompt_inputs() -> "RunConfig":
    """Prompt for the five Section-2 inputs, then build a config."""
    print("\n=== RAG-EVDA inputs ===")
    brand = input("1) Target brand name: ").strip()
    while not brand:
        brand = input("   (required) Target brand name: ").strip()

    raw = input("2) Industry topics (3-10), comma-separated: ")
    topics = [t.strip() for t in raw.split(",") if t.strip()]
    while len(topics) < 1:
        raw = input("   (required) at least one topic, comma-separated: ")
        topics = [t.strip() for t in raw.split(",") if t.strip()]

    raw = input("3) Competitor entities (2-5), comma-separated: ")
    comps = [c.strip() for c in raw.split(",") if c.strip()]
    while len(comps) < 1:
        raw = input("   (required) at least one competitor, comma-separated: ")
        comps = [c.strip() for c in raw.split(",") if c.strip()]

    depth_raw = input("4) Crawl depth per query (default 50): ").strip()
    depth = int(depth_raw) if depth_raw.isdigit() else 50

    locality = input("5) Locality / geo target (optional, e.g. US/UK): ").strip()
    locality = locality or None

    harvester = input("   Harvester [duckduckgo/searxng/file] (default duckduckgo): ").strip() or "duckduckgo"

    searxng_url = None
    corpus_dir = None
    if harvester == "searxng":
        searxng_url = input("   SearXNG base URL (e.g. http://localhost:8080): ").strip() or None
    elif harvester == "file":
        corpus_dir = input("   Local corpus directory (HTML/MD/TXT/PDF): ").strip() or None

    print(f"\nRunning audit for '{brand}' with {len(topics)} topics, "
          f"{len(comps)} competitors, depth {depth}...\n")
    return RunConfig(
        target_brand=brand,
        industry_topics=topics,
        competitor_entities=comps,
        crawl_depth=depth,
        locality=locality,
        harvester=harvester,
        searxng_base_url=searxng_url,
        corpus_dir=corpus_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
