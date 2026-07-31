"""Job Aggregator — main orchestrator.

Loads companies.yaml, dispatches fetchers by ATS type, applies filters,
deduplicates, and generates output (JSON + HTML dashboard).

Usage:
  python main.py                          # default run
  python main.py --verbose                # detailed logging
  python main.py --skip-workday           # skip Workday companies (if blocked)
  python main.py --workday-delay 5        # slower Workday pacing
  python main.py --config my_companies.yaml --output-dir results/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from fetchers import fetch_ashby, fetch_greenhouse, fetch_lever, fetch_workday, fetch_amazon, fetch_sap, fetch_servicenow
from fetchers.fetch_swiggy import fetch_swiggy_jobs
from fetchers.fetch_gs import fetch_gs_jobs
from fetchers.fetch_eightfold import fetch_eightfold
from fetchers.fetch_phenom import fetch_phenom
from fetchers.fetch_turbohire import fetch_turbohire
from fetchers.fetch_sitemap import fetch_sitemap_jobs
from fetchers.fetch_oracle import fetch_oracle_jobs
from filter import apply_filters

# Dashboard import — may not exist yet during development
try:
    from generate_dashboard import generate_dashboard
except ImportError:
    generate_dashboard = None  # type: ignore[assignment]

logger = logging.getLogger("job_aggregator")


# ── Config loader ────────────────────────────────────────────────────────────

def load_companies(config_path: str) -> list[dict]:
    """Load and validate companies.yaml."""
    path = Path(config_path)
    if not path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    companies = data.get("companies", [])
    enabled = [c for c in companies if c.get("enabled", True)]
    logger.info("Loaded %d companies (%d enabled)", len(companies), len(enabled))
    return enabled


def group_by_ats(companies: list[dict]) -> dict[str, list[dict]]:
    """Group companies by ATS type."""
    groups: dict[str, list[dict]] = {}
    for c in companies:
        ats = c.get("ats", "custom")
        groups.setdefault(ats, []).append(c)
    return groups


# ── Fetch orchestration ──────────────────────────────────────────────────────

async def fetch_all(
    groups: dict[str, list[dict]],
    skip_workday: bool = False,
    workday_delay: float = 3.0,
) -> tuple[list[dict], list[dict]]:
    """Fetch jobs from all companies, grouped by ATS type.

    Returns:
        (all_jobs, custom_ats_companies)
    """
    all_jobs: list[dict] = []
    custom_ats_companies: list[dict] = []

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"Accept": "application/json"},
    ) as client:
        # ── Greenhouse (parallel, no rate concern) ──
        greenhouse_cos = groups.get("greenhouse", [])
        if greenhouse_cos:
            logger.info("Fetching %d Greenhouse companies...", len(greenhouse_cos))
            tasks = [
                fetch_greenhouse(client, c["slug"], c["name"])
                for c in greenhouse_cos
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for co, result in zip(greenhouse_cos, results):
                if isinstance(result, Exception):
                    logger.error("[Greenhouse/%s] failed: %s", co["name"], result)
                else:
                    all_jobs.extend(result)

        # ── Lever (parallel, low rate concern) ──
        lever_cos = groups.get("lever", [])
        if lever_cos:
            logger.info("Fetching %d Lever companies...", len(lever_cos))
            tasks = [
                fetch_lever(client, c["slug"], c["name"])
                for c in lever_cos
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for co, result in zip(lever_cos, results):
                if isinstance(result, Exception):
                    logger.error("[Lever/%s] failed: %s", co["name"], result)
                else:
                    all_jobs.extend(result)

        # ── Ashby (parallel, no rate concern) ──
        ashby_cos = groups.get("ashby", [])
        if ashby_cos:
            logger.info("Fetching %d Ashby companies...", len(ashby_cos))
            tasks = [
                fetch_ashby(client, c["slug"], c["name"])
                for c in ashby_cos
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for co, result in zip(ashby_cos, results):
                if isinstance(result, Exception):
                    logger.error("[Ashby/%s] failed: %s", co["name"], result)
                else:
                    all_jobs.extend(result)

        # ── Workday (sequential with delays — bot protection) ──
        workday_cos = groups.get("workday", [])
        if workday_cos and not skip_workday:
            logger.info(
                "Fetching %d Workday companies (sequential, %.1fs delay)...",
                len(workday_cos), workday_delay,
            )
            for co in workday_cos:
                try:
                    jobs = await fetch_workday(
                        client,
                        co["tenant"],
                        co["wd_instance"],
                        co["site"],
                        co["name"],
                        search_text="India",
                        delay=workday_delay,
                    )
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Workday/%s] failed: %s", co["name"], exc)

                # Extra delay between different Workday tenants
                if co != workday_cos[-1]:
                    await asyncio.sleep(2.0)
        elif workday_cos and skip_workday:
            logger.info(
                "Skipping %d Workday companies (--skip-workday flag)",
                len(workday_cos),
            )
            # Still add them to custom_ats for manual check notification
            for co in workday_cos:
                custom_ats_companies.append({
                    "name": co["name"],
                    "careers_url": co.get("careers_url", ""),
                })
                
        # ── Amazon (custom JSON API) ──
        amazon_cos = groups.get("amazon", [])
        if amazon_cos:
            logger.info("Fetching %d Amazon companies...", len(amazon_cos))
            for co in amazon_cos:
                try:
                    jobs = await fetch_amazon(client)
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Amazon/%s] failed: %s", co["name"], exc)

        # ── Apify / Cloud Scraped ──
        apify_cos = groups.get("apify", [])
        if apify_cos:
            logger.info("Fetching %d Apify companies...", len(apify_cos))
            for co in apify_cos:
                try:
                    jobs = await fetch_apify(co["name"], co.get("careers_url", ""))
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Apify/%s] failed: %s", co["name"], exc)

        # ── SAP Labs India (HTML Table) ──
        sap_cos = groups.get("sap", [])
        if sap_cos:
            logger.info("Fetching %d SAP companies...", len(sap_cos))
            for co in sap_cos:
                try:
                    jobs = await fetch_sap(client, co["name"], co.get("careers_url", "https://jobs.sap.com"))
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[SAP/%s] failed: %s", co["name"], exc)

        # ── ServiceNow (Sitemap) ──
        servicenow_cos = groups.get("servicenow", [])
        if servicenow_cos:
            logger.info("Fetching %d ServiceNow companies...", len(servicenow_cos))
            for co in servicenow_cos:
                try:
                    jobs = await fetch_servicenow(client, co["name"], co.get("careers_url", "https://careers.servicenow.com"))
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[ServiceNow/%s] failed: %s", co["name"], exc)

        # ── Swiggy (Native) ──
        swiggy_cos = groups.get("swiggy", [])
        if swiggy_cos:
            logger.info("Fetching %d Swiggy companies...", len(swiggy_cos))
            for co in swiggy_cos:
                try:
                    jobs = await fetch_swiggy_jobs(client, co)
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Swiggy/%s] failed: %s", co["name"], exc)

        # ── Eightfold (API) ──
        eightfold_cos = groups.get("eightfold", [])
        if eightfold_cos:
            logger.info("Fetching %d Eightfold companies...", len(eightfold_cos))
            for co in eightfold_cos:
                try:
                    jobs = await fetch_eightfold(client, co["name"], co["slug"])
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Eightfold/%s] failed: %s", co["name"], exc)
                    
        # ── Phenom ──
        phenom_cos = groups.get("phenom", [])
        if phenom_cos:
            logger.info("Fetching %d Phenom companies...", len(phenom_cos))
            for co in phenom_cos:
                try:
                    lang = co.get("lang", "en_us")
                    country = co.get("country", "us")
                    jobs = await fetch_phenom(client, co["name"], co["slug"], lang, country)
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Phenom/%s] failed: %s", co["name"], exc)
                    
        # ── Turbohire ──
        turbohire_cos = groups.get("turbohire", [])
        if turbohire_cos:
            logger.info("Fetching %d Turbohire companies...", len(turbohire_cos))
            for co in turbohire_cos:
                try:
                    jobs = await fetch_turbohire(client, co["name"], co["org_id"])
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Turbohire/%s] failed: %s", co["name"], exc)

        # ── Sitemap (General) ──
        sitemap_cos = groups.get("sitemap", [])
        if sitemap_cos:
            logger.info("Fetching %d Sitemap companies...", len(sitemap_cos))
            for co in sitemap_cos:
                try:
                    jobs = await fetch_sitemap_jobs(client, co)
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[Sitemap/%s] failed: %s", co["name"], exc)

        # ── Oracle Cloud HCM ──
        oracle_cos = groups.get("oracle", [])
        if oracle_cos:
            logger.info("Fetching %d Oracle Cloud companies...", len(oracle_cos))
            try:
                from fetchers.fetch_oracle import fetch_oracle_jobs
                jobs = fetch_oracle_jobs(oracle_cos)
                all_jobs.extend(jobs)
            except Exception as exc:
                logger.error("[Oracle] failed: %s", exc)

        # ── Goldman Sachs GraphQL ──
        gs_cos = groups.get("gs_graphql", [])
        if gs_cos:
            logger.info("Fetching %d GS GraphQL companies...", len(gs_cos))
            for co in gs_cos:
                try:
                    jobs = fetch_gs_jobs(co["name"])
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error("[GS GraphQL/%s] failed: %s", co["name"], exc)

        # ── DOM Scraper (Playwright) ──
        dom_cos = groups.get("dom_scraper", [])
        if dom_cos:
            logger.info("Fetching %d companies via Playwright DOM Scraper...", len(dom_cos))
            from fetchers.fetch_dom import fetch_all_dom
            try:
                dom_jobs = await fetch_all_dom(dom_cos)
                all_jobs.extend(dom_jobs)
            except Exception as exc:
                logger.error("[DOM Scraper] failed: %s", exc)

        # ── Custom ATS (no API — flag for manual check) ──
        custom_cos = groups.get("custom", [])
        for co in custom_cos:
            custom_ats_companies.append({
                "name": co["name"],
                "careers_url": co.get("careers_url", ""),
            })
        if custom_cos:
            logger.info(
                "Flagged %d custom-ATS companies for manual checking: %s",
                len(custom_cos),
                ", ".join(c["name"] for c in custom_cos),
            )

    return all_jobs, custom_ats_companies


# ── Output ───────────────────────────────────────────────────────────────────

def save_json(jobs: list[dict], output_path: str) -> None:
    """Save jobs to JSON file."""
    # Remove raw_content (large HTML) from JSON output to keep file size sane
    clean_jobs = []
    for j in jobs:
        clean = {k: v for k, v in j.items() if k != "raw_content"}
        clean_jobs.append(clean)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean_jobs, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d jobs → %s", len(clean_jobs), output_path)


def print_summary(
    total_raw: int,
    total_filtered: int,
    custom_ats: list[dict],
    elapsed: float,
) -> None:
    """Print a human-readable summary."""
    print("\n" + "=" * 60)
    print("  JOB AGGREGATOR -- RUN SUMMARY")
    print("=" * 60)
    print(f"  Raw jobs fetched   : {total_raw}")
    print(f"  After all filters  : {total_filtered}")
    print(f"  Time elapsed       : {elapsed:.1f}s")

    if custom_ats:
        print(f"\n  [!] Manual check needed ({len(custom_ats)} companies):")
        for co in custom_ats:
            print(f"     - {co['name']}: {co['careers_url']}")

    print("=" * 60 + "\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Job Aggregator — fetch FTE roles from company ATS APIs"
    )
    ap.add_argument(
        "--config", default="companies.yaml",
        help="Path to companies.yaml (default: companies.yaml)",
    )
    ap.add_argument(
        "--output-dir", default="output",
        help="Output directory for JSON + HTML (default: output/)",
    )
    ap.add_argument(
        "--workday-delay", type=float, default=3.0,
        help="Delay in seconds between Workday API requests (default: 3.0)",
    )
    ap.add_argument(
        "--skip-workday", action="store_true",
        help="Skip all Workday companies (use if getting blocked)",
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose/debug logging",
    )
    return ap.parse_args()


async def run() -> None:
    args = parse_args()

    # Logging setup
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    start = time.monotonic()

    # Load config
    companies = load_companies(args.config)
    
    # Run ATS detector for companies missing 'ats' field
    from ats_detector import detect_ats
    for c in companies:
        if "ats" not in c and "careers_url" in c:
            logger.info("Auto-detecting ATS for %s...", c["name"])
            detected = await detect_ats(c["careers_url"])
            c.update(detected)
            if detected.get("ats") != "custom":
                logger.info("  -> Detected as %s!", detected.get("ats"))
            else:
                logger.info("  -> Unsupported ATS (%s). Marked for manual check.", detected.get("reason", "unknown"))

    groups = group_by_ats(companies)

    for ats, cos in groups.items():
        logger.info("  %s: %s", ats.upper(), ", ".join(c["name"] for c in cos))

    # Fetch
    all_jobs, custom_ats = await fetch_all(
        groups,
        skip_workday=args.skip_workday,
        workday_delay=args.workday_delay,
    )
    total_raw = len(all_jobs)
    logger.info("Total raw jobs fetched: %d", total_raw)

    if not all_jobs:
        print("\nERROR: No jobs fetched. Check your internet connection and company configs.")
        if custom_ats:
            print("\n  These companies need manual checking:")
            for co in custom_ats:
                print(f"    • {co['name']}: {co['careers_url']}")
        return

    # Filter
    filtered = apply_filters(all_jobs)

    # --- History Tracking & Anomaly Detection ---
    output_dir = Path(args.output_dir)
    history_file = output_dir / "history.json"
    history = {}
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception as e:
            logger.warning("Failed to load history.json: %s", e)

    raw_counts = {}
    for j in all_jobs:
        c = j.get("company", "Unknown")
        raw_counts[c] = raw_counts.get(c, 0) + 1

    company_metadata = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # We should also track companies that yielded 0 jobs in this run if they are in the groups
    all_attempted = set()
    for _, cos in groups.items():
        for c in cos:
            all_attempted.add(c["name"])

    for c_name in all_attempted:
        current_count = raw_counts.get(c_name, 0)
        c_hist = history.get(c_name, {"count": 0, "last_success": "Never", "historical_avg": 0})
        
        anomaly = False
        prev_count = c_hist.get("count", 0)
        avg = c_hist.get("historical_avg", prev_count)
        
        if current_count == 0 and prev_count > 0:
            anomaly = True
            reason = "Count dropped to 0"
        elif prev_count > 0 and current_count < (avg * 0.3):
            anomaly = True
            reason = f"Drastic drop from avg {avg:.1f} to {current_count}"
        else:
            reason = ""
            
        company_metadata[c_name] = {
            "current_count": current_count,
            "previous_count": prev_count,
            "last_success": c_hist.get("last_success", "Never"),
            "anomaly": anomaly,
            "anomaly_reason": reason
        }
        
        # Update history if > 0
        if current_count > 0:
            new_avg = current_count if avg == 0 else (avg + current_count) / 2
            history[c_name] = {
                "count": current_count,
                "last_success": now_iso,
                "historical_avg": new_avg
            }

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    # ---------------------------------------------

    # Output
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "jobs.json"
    save_json(filtered, str(json_path))

    html_path = output_dir / "dashboard.html"
    if generate_dashboard is not None:
        generate_dashboard(filtered, str(html_path), custom_ats, company_metadata)
        logger.info("Dashboard → %s", html_path)
    else:
        logger.warning(
            "generate_dashboard not available — skipping HTML output. "
            "JSON output is still saved."
        )

    elapsed = time.monotonic() - start
    print_summary(total_raw, len(filtered), custom_ats, elapsed)

    print(f"  JSON  : {json_path.resolve()}")
    if html_path.exists():
        print(f"  HTML  : {html_path.resolve()}")
    print()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
