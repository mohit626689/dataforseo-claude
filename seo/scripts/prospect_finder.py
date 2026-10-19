#!/usr/bin/env python3
"""Find local-business prospects with broken SEO.

Pipeline (all live DataForSEO endpoints):
  1. SERP API search for "<niche> <city>" → top organic results
  2. Filter out aggregators (Yelp, Yellow Pages, Angi, Maps, etc.)
  3. For each candidate domain, in parallel batches:
        a) Labs domain_rank_overview  → traffic + keyword count
        b) On-Page instant_pages       → technical issues on homepage
        c) Backlinks summary           → authority signals
  4. Compute closeability score (prefers small, ranking-but-weak sites)
  5. Sort by score, return JSON

Usage:
  prospect_finder.py find --niche "plumbers" --city "San Francisco CA"
                          [--limit 30] [--location "United States"]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import math
import sys
from typing import Any

from dataforseo_client import (
    DEFAULT_LANGUAGE,
    DEFAULT_LOCATION,
    DataForSEOError,
    call,
    first_result,
    normalize_domain,
    write_json,
)

# Aggregators / directories / non-target domains to skip from SERP results.
AGGREGATOR_DOMAINS = {
    "yelp.com", "yellowpages.com", "bbb.org", "angi.com", "homeadvisor.com",
    "thumbtack.com", "houzz.com", "nextdoor.com", "facebook.com",
    "linkedin.com", "youtube.com", "instagram.com", "tiktok.com", "x.com",
    "twitter.com", "google.com", "maps.google.com", "bing.com",
    "mapquest.com", "foursquare.com", "citysearch.com", "merchantcircle.com",
    "expertise.com", "threebestrated.com", "bestcompany.com", "yp.com",
    "superpages.com", "manta.com", "porch.com", "trustpilot.com",
    "consumeraffairs.com", "indeed.com", "glassdoor.com", "wikipedia.org",
    "reddit.com", "quora.com", "medium.com",
}


def serp_candidates(niche: str, city: str, location: str, language: str,
                    depth: int) -> list[dict[str, Any]]:
    """SERP search → list of unique candidate domains with their positions."""
    payload = {
        "keyword": f"{niche} {city}",
        "location_name": location,
        "language_code": language,
        "device": "desktop",
        "os": "windows",
        "depth": depth,
    }
    data = call("serp/google/organic/live/advanced", payload)
    result = first_result(data)
    items = result.get("items") or []

    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") != "organic":
            continue
        domain = normalize_domain(item.get("domain") or "")
        if not domain or domain in AGGREGATOR_DOMAINS or domain in seen:
            continue
        seen.add(domain)
        candidates.append({
            "domain": domain,
            "position": item.get("rank_absolute") or item.get("rank_group"),
            "url": item.get("url"),
            "title": item.get("title"),
            "description": item.get("description"),
        })
    return candidates


def enrich_domain(domain: str, location: str, language: str) -> dict[str, Any]:
    """Pull overview + technical issues + backlinks for a single domain."""
    enrichment: dict[str, Any] = {
        "overview": None,
        "technical_issues": [],
        "backlinks": None,
        "errors": [],
    }

    # Overview (Labs)
    try:
        data = call("dataforseo_labs/google/domain_rank_overview/live", {
            "target": domain,
            "location_name": location,
            "language_code": language,
        })
        result = first_result(data)
        if result.get("items"):
            metrics = result["items"][0].get("metrics", {}).get("organic", {})
            enrichment["overview"] = {
                "estimated_traffic": metrics.get("etv"),
                "ranking_keywords": metrics.get("count"),
                "top_10_keywords": metrics.get("pos_1", 0) + metrics.get("pos_2_3", 0) + metrics.get("pos_4_10", 0),
            }
    except DataForSEOError as exc:
        enrichment["errors"].append(f"overview: {exc}")

    # Technical issues on homepage (On-Page)
    try:
        data = call("on_page/instant_pages", {
            "url": f"https://{domain}",
            "enable_javascript": False,
            "load_resources": False,
        })
        result = first_result(data)
        items = result.get("items") or []
        if items:
            checks = items[0].get("checks") or {}
            issues = []
            # Surface notable failures
            issue_map = {
                "no_title": "Missing page title",
                "no_description": "Missing meta description",
                "no_h1_tag": "Missing H1 tag",
                "is_https": "Site not on HTTPS",
                "has_render_blocking_resources": "Render-blocking resources slow page load",
                "low_content_rate": "Thin content on homepage",
                "duplicate_title_tag": "Duplicate title tag",
                "duplicate_description": "Duplicate meta description",
                "duplicate_meta_tags": "Duplicate meta tags",
                "is_redirect": "Page redirects",
                "is_4xx_code": "Page returns 4xx error",
                "is_5xx_code": "Page returns 5xx error",
            }
            for key, label in issue_map.items():
                val = checks.get(key)
                # Some keys are "true = problem", others "false = problem"
                if key == "is_https":
                    if val is False:
                        issues.append(label)
                else:
                    if val is True:
                        issues.append(label)
            enrichment["technical_issues"] = issues
    except DataForSEOError as exc:
        enrichment["errors"].append(f"on_page: {exc}")

    # Backlinks summary
    try:
        data = call("backlinks/summary/live", {
            "target": domain,
            "internal_list_limit": 1,
        })
        summary = first_result(data)
        enrichment["backlinks"] = {
            "backlinks": summary.get("backlinks"),
            "referring_domains": summary.get("referring_domains"),
            "rank": summary.get("rank"),
        }
    except DataForSEOError as exc:
        enrichment["errors"].append(f"backlinks: {exc}")

    return enrichment


def compute_closeability(prospect: dict[str, Any]) -> float:
    """Score 0-100. Higher = easier to close as a client.

    Heuristic:
      - position_score: peaks for sites on page 2-3 (position 11-30).
        Page 1 sites are already winning. Page 5+ aren't trying.
      - issues_score: more visible issues = clearer pitch (cap 30).
      - size_score: small sites are easier to land than enterprise.
        Inverse log of referring domains, capped.
      - ranking_score: must have *some* keyword footprint (so they care
        about SEO) but not a massive one (so they're not already paying).
    """
    score = 0.0

    pos = prospect.get("position") or 50
    if 11 <= pos <= 30:
        position_score = 30
    elif 4 <= pos <= 10:
        position_score = 20
    elif 31 <= pos <= 60:
        position_score = 15
    else:
        position_score = 5
    score += position_score

    issues_count = len(prospect.get("technical_issues") or [])
    score += min(issues_count * 5, 25)

    refdomains = (prospect.get("backlinks") or {}).get("referring_domains") or 0
    # Sweet spot: 5-100 referring domains. Smaller = too tiny to care, larger = too established.
    if 5 <= refdomains <= 100:
        score += 20
    elif refdomains < 5:
        score += 10
    elif refdomains <= 500:
        score += 12
    else:
        score += 5

    keywords = (prospect.get("overview") or {}).get("ranking_keywords") or 0
    if 50 <= keywords <= 500:
        score += 25
    elif keywords < 50:
        score += 10
    elif keywords <= 2000:
        score += 18
    else:
        score += 8

    return min(round(score, 1), 100.0)


def cmd_find(args: argparse.Namespace) -> None:
    """Find prospects for a niche + city combo."""
    sys.stderr.write(f"→ Searching '{args.niche} {args.city}'...\n")
    candidates = serp_candidates(
        args.niche, args.city, args.location, args.language, args.depth,
    )
    if not candidates:
        write_json({"niche": args.niche, "city": args.city, "prospects": []}, args.out)
        return

    sys.stderr.write(f"→ Found {len(candidates)} non-aggregator domains. Enriching top {args.limit}...\n")
    candidates = candidates[:args.limit]

    # Parallel enrichment (each domain = 3 API calls, but we batch domains in threads)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallelism) as ex:
        futures = {
            ex.submit(enrich_domain, c["domain"], args.location, args.language): c
            for c in candidates
        }
        for fut in concurrent.futures.as_completed(futures):
            candidate = futures[fut]
            try:
                candidate.update(fut.result())
            except Exception as exc:
                candidate["errors"] = [f"enrichment failed: {exc}"]

    # Score and sort
    for c in candidates:
        c["closeability_score"] = compute_closeability(c)
    candidates.sort(key=lambda c: c["closeability_score"], reverse=True)

    write_json({
        "niche": args.niche,
        "city": args.city,
        "location": args.location,
        "candidates_checked": len(candidates),
        "prospects": candidates,
    }, args.out)
    sys.stderr.write(f"✓ Done. Top closeability: {candidates[0]['closeability_score']}/100\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="DataForSEO prospect finder.")
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--out", "-o", default="-")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_find = sub.add_parser("find", help="Find local-business SEO prospects.")
    p_find.add_argument("--niche", required=True, help="e.g. 'plumbers' or 'HVAC'")
    p_find.add_argument("--city", required=True, help="e.g. 'San Francisco CA'")
    p_find.add_argument("--limit", type=int, default=30, help="Max prospects to enrich.")
    p_find.add_argument("--depth", type=int, default=50, help="SERP depth to search.")
    p_find.add_argument("--parallelism", type=int, default=5,
                        help="Concurrent enrichment workers.")
    p_find.set_defaults(func=cmd_find)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
