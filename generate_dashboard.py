"""
generate_dashboard.py
Generates a single self-contained HTML dashboard for job listings.
All CSS and JS are inlined — the only external dependency is Google Fonts CDN.
"""

from __future__ import annotations

import html
import json
from datetime import datetime


def generate_dashboard(
    jobs: list[dict],
    output_path: str,
    custom_ats_companies: list[dict] | None = None,
    company_metadata: dict | None = None,
) -> None:
    """Write a self-contained HTML dashboard to *output_path*.

    Parameters
    ----------
    jobs:
        Each dict must contain: company, title, location, employment_type,
        ats_source, apply_url, date_fetched, description, departments.
    output_path:
        Filesystem path for the generated HTML file.
    custom_ats_companies:
        Optional list of ``{"name": …, "careers_url": …}`` dicts for
        companies whose ATS could not be scraped automatically.
    company_metadata:
        Optional dict mapping company names to their history/anomaly metadata.
    """
    if custom_ats_companies is None:
        custom_ats_companies = []
    if company_metadata is None:
        company_metadata = {}

    # ------------------------------------------------------------------
    # Gather stats
    # ------------------------------------------------------------------
    total_jobs = len(jobs)
    unique_companies = sorted({j["company"] for j in jobs})
    unique_ats = sorted({j.get("ats_source", "Unknown") for j in jobs})
    num_companies = len(unique_companies)
    latest_fetch = max((j.get("date_fetched", "N/A") for j in jobs), default="N/A")
    generated_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Build table rows JSON (passed to JS)
    # ------------------------------------------------------------------
    rows_for_js: list[dict] = []
    
    def is_invalid_nav(title: str) -> bool:
        t = title.lower()
        bad_phrases = ["skip to", "home", "why work here", "university hiring", "apply now", "main content", "back to", "careers", "jobs"]
        if len(t) < 4:
            return True
        for phrase in bad_phrases:
            if phrase in t:
                return True
        # Check if it has real words
        words = t.split()
        if len(words) < 2 and not any(w in t for w in ["engineer", "developer", "manager", "analyst", "intern", "lead", "director"]):
            pass # A bit risky to fail on single words, but we rely on other checks mostly
        return False

    for j in jobs:
        emp_type = j.get("employment_type", "")
        if emp_type == "Unknown":
            emp_type = "N/A"

        invalid = is_invalid_nav(j.get("title", ""))

        rows_for_js.append(
            {
                "company": j.get("company", ""),
                "title": j.get("title", ""),
                "location": j.get("location", ""),
                "employment_type": emp_type,
                "ats_source": j.get("ats_source", ""),
                "apply_url": j.get("apply_url", ""),
                "date_fetched": j.get("date_fetched", ""),
                "description": j.get("description", ""),
                "departments": j.get("departments", ""),
                "invalid": invalid
            }
        )

    rows_json = json.dumps(rows_for_js, ensure_ascii=False)
    companies_json = json.dumps(unique_companies, ensure_ascii=False)
    ats_json = json.dumps(unique_ats, ensure_ascii=False)
    meta_json = json.dumps(company_metadata, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Custom ATS card HTML
    # ------------------------------------------------------------------
    custom_ats_html = ""
    if custom_ats_companies:
        items = ""
        for c in custom_ats_companies:
            name = html.escape(c["name"])
            url = html.escape(c["careers_url"])
            items += (
                f'<a href="{url}" target="_blank" rel="noopener" class="custom-ats-link">'
                f'<span class="custom-ats-name">{name}</span>'
                f'<span class="custom-ats-arrow">&#8599;</span>'
                f"</a>\n"
            )
        custom_ats_html = f"""
        <section class="custom-ats-card fade-in" style="animation-delay:.45s">
            <div class="custom-ats-header">
                <span class="custom-ats-icon">&#9888;</span>
                <h3>Not Yet Integrated</h3>
            </div>
            <p class="custom-ats-desc">The following companies use non-standard career pages that couldn't be scraped automatically. Click to visit their careers page directly.</p>
            <div class="custom-ats-grid">
                {items}
            </div>
        </section>
        """

    # ------------------------------------------------------------------
    # Full HTML
    # ------------------------------------------------------------------
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Job Aggregator Dashboard — {total_jobs} listings across {num_companies} companies">
<title>Job Dashboard — {total_jobs} Listings</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
/* ============================================================
   CSS CUSTOM PROPERTIES
   ============================================================ */
:root {{
    --bg-primary:    #0a0e1a;
    --bg-secondary:  #111827;
    --bg-card:       rgba(17, 24, 39, 0.65);
    --bg-card-hover: rgba(30, 41, 59, 0.80);
    --bg-glass:      rgba(255, 255, 255, 0.04);
    --bg-glass-border: rgba(255, 255, 255, 0.08);

    --text-primary:   #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted:     #64748b;

    --accent:         #6366f1;
    --accent-glow:    rgba(99, 102, 241, 0.35);
    --accent-light:   #818cf8;
    --accent-surface: rgba(99, 102, 241, 0.12);

    --success:        #34d399;
    --warning:        #fbbf24;
    --warning-surface: rgba(251, 191, 36, 0.10);
    --danger:         #f87171;

    --border:         rgba(255, 255, 255, 0.06);
    --border-hover:   rgba(255, 255, 255, 0.12);

    --radius:         12px;
    --radius-sm:      8px;
    --radius-lg:      20px;
    --radius-full:    9999px;

    --shadow-sm:  0 1px 2px rgba(0,0,0,.3);
    --shadow-md:  0 4px 16px rgba(0,0,0,.4);
    --shadow-lg:  0 8px 32px rgba(0,0,0,.5);
    --shadow-glow: 0 0 40px var(--accent-glow);

    --transition-fast: 150ms cubic-bezier(.4,0,.2,1);
    --transition-base: 250ms cubic-bezier(.4,0,.2,1);
    --transition-slow: 400ms cubic-bezier(.4,0,.2,1);
}}

/* ============================================================
   RESET & BASE
   ============================================================ */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
    overflow-x: hidden;
}}

/* Animated background mesh */
body::before {{
    content: '';
    position: fixed;
    inset: 0;
    z-index: -1;
    background:
        radial-gradient(ellipse 80% 50% at 20% 20%, rgba(99,102,241,.08) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 80% 80%, rgba(52,211,153,.06) 0%, transparent 60%),
        radial-gradient(ellipse 50% 60% at 50% 10%, rgba(248,113,113,.04) 0%, transparent 50%);
    animation: bgShift 20s ease-in-out infinite alternate;
}}
@keyframes bgShift {{
    0%   {{ opacity: .7; transform: scale(1); }}
    100% {{ opacity: 1;  transform: scale(1.08); }}
}}

/* ============================================================
   LAYOUT
   ============================================================ */
.container {{
    max-width: 1440px;
    margin: 0 auto;
    padding: 2rem 2rem 4rem;
}}

/* ============================================================
   ANIMATIONS
   ============================================================ */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(24px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
.fade-in {{
    animation: fadeInUp .6s var(--transition-slow) both;
}}
@keyframes pulse {{
    0%, 100% {{ transform: scale(1); }}
    50%      {{ transform: scale(1.06); }}
}}
@keyframes shimmer {{
    0%   {{ background-position: -200% 0; }}
    100% {{ background-position: 200% 0; }}
}}

/* ============================================================
   HEADER / HERO
   ============================================================ */
header {{
    text-align: center;
    margin-bottom: 2.5rem;
}}
header h1 {{
    font-size: clamp(2rem, 5vw, 3.2rem);
    font-weight: 900;
    letter-spacing: -0.03em;
    background: linear-gradient(135deg, var(--text-primary) 0%, var(--accent-light) 50%, var(--success) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: .4rem;
}}
header p {{
    color: var(--text-secondary);
    font-size: 1.05rem;
    font-weight: 400;
}}

/* ============================================================
   STAT CARDS  (glassmorphism)
   ============================================================ */
.stats-row {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1.25rem;
    margin-bottom: 2rem;
}}
.stat-card {{
    background: var(--bg-glass);
    backdrop-filter: blur(16px) saturate(1.4);
    -webkit-backdrop-filter: blur(16px) saturate(1.4);
    border: 1px solid var(--bg-glass-border);
    border-radius: var(--radius-lg);
    padding: 1.5rem 1.75rem;
    position: relative;
    overflow: hidden;
    transition: transform var(--transition-base), box-shadow var(--transition-base);
}}
.stat-card:hover {{
    transform: translateY(-4px);
    box-shadow: var(--shadow-glow);
}}
.stat-card::after {{
    content: '';
    position: absolute;
    inset: 0;
    border-radius: var(--radius-lg);
    background: linear-gradient(135deg, rgba(99,102,241,.08), transparent 60%);
    pointer-events: none;
}}
.stat-label {{
    font-size: .8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: var(--text-muted);
    margin-bottom: .35rem;
}}
.stat-value {{
    font-size: 2rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.1;
}}
.stat-value.accent {{ color: var(--accent-light); }}
.stat-value.green  {{ color: var(--success); }}
.stat-sub {{
    font-size: .78rem;
    color: var(--text-muted);
    margin-top: .3rem;
}}

/* ============================================================
   CONTROLS  (filters & search)
   ============================================================ */
.controls {{
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 1.5rem;
    align-items: center;
}}
.search-wrap {{
    flex: 1 1 320px;
    position: relative;
}}
.search-wrap svg {{
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    width: 18px;
    height: 18px;
    stroke: var(--text-muted);
    fill: none;
    stroke-width: 2;
    pointer-events: none;
    transition: stroke var(--transition-fast);
}}
.search-wrap:focus-within svg {{
    stroke: var(--accent-light);
}}
.search-input {{
    width: 100%;
    padding: .75rem 1rem .75rem 2.75rem;
    background: var(--bg-glass);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: var(--radius-full);
    color: var(--text-primary);
    font-family: inherit;
    font-size: .92rem;
    outline: none;
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}}
.search-input::placeholder {{ color: var(--text-muted); }}
.search-input:focus {{
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow);
}}

.filter-select {{
    padding: .72rem 2.4rem .72rem 1rem;
    background: var(--bg-glass);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: var(--radius-full);
    color: var(--text-primary);
    font-family: inherit;
    font-size: .88rem;
    cursor: pointer;
    outline: none;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394a3b8' d='M6 8.5L1 3.5h10z'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}}
.filter-select:focus {{
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow);
}}
.filter-select option {{
    background: var(--bg-secondary);
    color: var(--text-primary);
}}

.result-count {{
    font-size: .85rem;
    color: var(--text-muted);
    white-space: nowrap;
    margin-left: auto;
    font-weight: 500;
}}
.result-count span {{
    color: var(--accent-light);
    font-weight: 700;
}}

/* ============================================================
   TABLE
   ============================================================ */
.table-wrap {{
    background: var(--bg-glass);
    backdrop-filter: blur(18px) saturate(1.3);
    -webkit-backdrop-filter: blur(18px) saturate(1.3);
    border: 1px solid var(--bg-glass-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-lg);
}}
.table-scroll {{
    overflow-x: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--accent) transparent;
}}
.table-scroll::-webkit-scrollbar {{ height: 6px; }}
.table-scroll::-webkit-scrollbar-track {{ background: transparent; }}
.table-scroll::-webkit-scrollbar-thumb {{
    background: var(--accent);
    border-radius: 3px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    min-width: 960px;
}}
thead {{
    position: sticky;
    top: 0;
    z-index: 2;
}}
thead th {{
    background: rgba(15, 23, 42, 0.92);
    backdrop-filter: blur(6px);
    padding: 1rem 1.1rem;
    font-size: .78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .07em;
    color: var(--text-secondary);
    text-align: left;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    transition: color var(--transition-fast);
    position: relative;
}}
thead th:hover {{
    color: var(--accent-light);
}}
thead th .sort-arrow {{
    display: inline-block;
    margin-left: 5px;
    font-size: .7rem;
    opacity: .35;
    transition: opacity var(--transition-fast), transform var(--transition-fast);
}}
thead th.sort-active .sort-arrow {{
    opacity: 1;
    color: var(--accent-light);
}}
thead th.sort-desc .sort-arrow {{
    transform: rotate(180deg);
}}

tbody tr {{
    transition: background var(--transition-fast), transform var(--transition-fast);
}}
tbody tr:nth-child(even) {{
    background: rgba(255,255,255,.015);
}}
tbody tr:hover {{
    background: var(--bg-card-hover);
    transform: scale(1.002);
}}
tbody td {{
    padding: .85rem 1.1rem;
    font-size: .88rem;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
}}
tbody td:first-child {{
    color: var(--text-primary);
    font-weight: 600;
}}

/* Cell-specific */
.cell-title {{
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.cell-location {{
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

/* ATS badges */
.ats-badge {{
    display: inline-block;
    padding: .22rem .7rem;
    border-radius: var(--radius-full);
    font-size: .75rem;
    font-weight: 600;
    letter-spacing: .03em;
    white-space: nowrap;
}}
.ats-greenhouse  {{ background: rgba(52,211,153,.12); color: #6ee7b7; }}
.ats-lever        {{ background: rgba(251,191,36,.12); color: #fcd34d; }}
.ats-workday      {{ background: rgba(96,165,250,.12); color: #93c5fd; }}
.ats-ashby        {{ background: rgba(232,121,249,.12); color: #e879f9; }}
.ats-default      {{ background: rgba(148,163,184,.10); color: #94a3b8; }}

/* Employment type pill */
.emp-pill {{
    display: inline-block;
    padding: .18rem .6rem;
    border-radius: var(--radius-full);
    font-size: .74rem;
    font-weight: 500;
    background: var(--accent-surface);
    color: var(--accent-light);
    white-space: nowrap;
}}

/* Apply button */
.apply-btn {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: .45rem 1rem;
    background: linear-gradient(135deg, var(--accent), #4f46e5);
    color: #fff;
    text-decoration: none;
    border-radius: var(--radius-full);
    font-size: .78rem;
    font-weight: 600;
    letter-spacing: .02em;
    white-space: nowrap;
    transition: transform var(--transition-fast), box-shadow var(--transition-fast), filter var(--transition-fast);
    box-shadow: 0 2px 8px rgba(99,102,241,.25);
}}
.apply-btn:hover {{
    transform: translateY(-2px) scale(1.04);
    box-shadow: 0 4px 20px rgba(99,102,241,.45);
    filter: brightness(1.12);
}}
.apply-btn:active {{
    transform: scale(.97);
}}
.apply-btn svg {{
    width: 13px; height: 13px;
    stroke: currentColor; fill: none; stroke-width: 2.5;
}}

/* Empty state */
.empty-state {{
    text-align: center;
    padding: 4rem 2rem;
    color: var(--text-muted);
}}
.empty-state .empty-icon {{
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: .5;
}}
.empty-state p {{
    font-size: 1rem;
}}

/* ============================================================
   CUSTOM ATS WARNING CARD
   ============================================================ */
.custom-ats-card {{
    margin-top: 2rem;
    background: var(--warning-surface);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(251,191,36,.18);
    border-radius: var(--radius-lg);
    padding: 1.75rem 2rem;
    box-shadow: var(--shadow-md);
}}
.custom-ats-header {{
    display: flex;
    align-items: center;
    gap: .65rem;
    margin-bottom: .6rem;
}}
.custom-ats-icon {{
    font-size: 1.5rem;
    line-height: 1;
    color: var(--warning);
}}
.custom-ats-header h3 {{
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--warning);
}}
.custom-ats-desc {{
    font-size: .88rem;
    color: var(--text-secondary);
    margin-bottom: 1.25rem;
    line-height: 1.55;
}}
.custom-ats-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: .75rem;
}}
.custom-ats-link {{
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    padding: .5rem 1.1rem;
    background: rgba(251,191,36,.08);
    border: 1px solid rgba(251,191,36,.2);
    border-radius: var(--radius-full);
    color: var(--warning);
    text-decoration: none;
    font-size: .84rem;
    font-weight: 600;
    transition: background var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}}
.custom-ats-link:hover {{
    background: rgba(251,191,36,.16);
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(251,191,36,.15);
}}
.custom-ats-arrow {{
    font-size: 1rem;
    transition: transform var(--transition-fast);
}}
.custom-ats-link:hover .custom-ats-arrow {{
    transform: translate(2px, -2px);
}}

/* ============================================================
   FOOTER
   ============================================================ */
footer {{
    text-align: center;
    padding: 3rem 1rem 1.5rem;
    color: var(--text-muted);
    font-size: .8rem;
    letter-spacing: .02em;
}}
footer span {{
    color: var(--accent-light);
}}

/* ============================================================
   RESPONSIVE
   ============================================================ */
@media (max-width: 768px) {{
    .container {{ padding: 1rem; }}
    .controls {{ flex-direction: column; }}
    .search-wrap {{ flex: 1 1 100%; }}
    .result-count {{ margin-left: 0; text-align: center; width: 100%; }}
    .stats-row {{ grid-template-columns: 1fr 1fr; gap: .85rem; }}
    .stat-card {{ padding: 1.1rem; }}
    .stat-value {{ font-size: 1.5rem; }}
}}
@media (max-width: 480px) {{
    .stats-row {{ grid-template-columns: 1fr; }}
}}
</style>
</head>

<body>
<div class="container">

    <!-- HEADER -->
    <header class="fade-in">
        <h1>&#128188; Job Dashboard</h1>
        <p>Your aggregated job listings in one place</p>
    </header>

    <!-- STATS -->
    <div class="stats-row">
        <div class="stat-card fade-in" style="animation-delay:.1s">
            <div class="stat-label">Total Listings</div>
            <div class="stat-value accent">{total_jobs}</div>
            <div class="stat-sub">Across all sources</div>
        </div>
        <div class="stat-card fade-in" style="animation-delay:.18s">
            <div class="stat-label">Companies</div>
            <div class="stat-value green">{num_companies}</div>
            <div class="stat-sub">Unique employers</div>
        </div>
        <div class="stat-card fade-in" style="animation-delay:.26s">
            <div class="stat-label">Last Fetched</div>
            <div class="stat-value" style="font-size:1.35rem">{html.escape(latest_fetch)}</div>
            <div class="stat-sub">Most recent scrape</div>
        </div>
        <div class="stat-card fade-in" style="animation-delay:.34s">
            <div class="stat-label">Generated</div>
            <div class="stat-value" style="font-size:1.15rem">{html.escape(generated_ts)}</div>
            <div class="stat-sub">Dashboard build time</div>
        </div>
    </div>

    <!-- CONTROLS -->
    <div class="controls fade-in" style="animation-delay:.38s">
        <div class="search-wrap">
            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" id="searchInput" class="search-input" placeholder="Search jobs, companies, locations…" autocomplete="off">
        </div>
        <select id="companyFilter" class="filter-select" aria-label="Filter by company">
            <option value="">All Companies</option>
        </select>
        <select id="atsFilter" class="filter-select" aria-label="Filter by ATS">
            <option value="">All ATS Sources</option>
        </select>
        <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; color:var(--text-secondary); cursor:pointer;">
            <input type="checkbox" id="indiaFilter" style="accent-color:var(--accent)"> India Only
        </label>
        <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; color:var(--text-secondary); cursor:pointer;">
            <input type="checkbox" id="highLpaFilter" style="accent-color:var(--accent)"> High Comp (>20LPA)
        </label>
        <div class="result-count">Showing <span id="visibleCount">{total_jobs}</span> of <span>{total_jobs}</span></div>
    </div>

    <!-- TABLE -->
    <div id="anomalyWarnings" style="margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem;"></div>

    <div class="table-wrap fade-in" style="animation-delay:.42s">
        <div class="table-scroll">
            <table id="jobTable">
                <thead>
                    <tr>
                        <th data-col="company">Company <span class="sort-arrow">&#9650;</span></th>
                        <th data-col="title">Title <span class="sort-arrow">&#9650;</span></th>
                        <th data-col="location">Location <span class="sort-arrow">&#9650;</span></th>
                        <th data-col="employment_type">Type <span class="sort-arrow">&#9650;</span></th>
                        <th data-col="ats_source">ATS Source <span class="sort-arrow">&#9650;</span></th>
                        <th data-col="apply">Apply <span class="sort-arrow" style="visibility:hidden">&#9650;</span></th>
                        <th data-col="date_fetched">Date Fetched <span class="sort-arrow">&#9650;</span></th>
                    </tr>
                </thead>
                <tbody id="jobBody"></tbody>
            </table>
        </div>
        <div class="empty-state" id="emptyState" style="display:none">
            <div class="empty-icon">&#128269;</div>
            <p>No jobs match your filters. Try adjusting your search.</p>
        </div>
    </div>

    {custom_ats_html}
</div>

<footer class="fade-in" style="animation-delay:.5s">
    Generated by <span>Job Aggregator</span> &bull; {html.escape(generated_ts)}
</footer>

<script>
(function() {{
"use strict";

/* ---------- DATA ---------- */
const JOBS = {rows_json};
const COMPANIES = {companies_json};
const ATS_LIST  = {ats_json};
const COMP_META = {meta_json};
const HIGH_COMP_TARGETS = new Set(["DE Shaw", "Postman", "Atlassian", "Rubrik", "Goldman Sachs", "Tower Research", "Salesforce", "NVIDIA", "ServiceNow", "Optiver", "Citadel Securities", "Google", "Microsoft", "Uber", "Figma", "CRED", "InMobi", "PhonePe", "Coinbase", "Razorpay"]);

/* ---------- DOM refs ---------- */
const tbody      = document.getElementById('jobBody');
const searchEl   = document.getElementById('searchInput');
const companyEl  = document.getElementById('companyFilter');
const atsEl      = document.getElementById('atsFilter');
const indiaEl    = document.getElementById('indiaFilter');
const highLpaEl  = document.getElementById('highLpaFilter');
const countEl    = document.getElementById('visibleCount');
const emptyEl    = document.getElementById('emptyState');
const tableEl    = document.getElementById('jobTable');

/* ---------- Populate selects ---------- */
COMPANIES.forEach(c => {{
    const o = document.createElement('option');
    o.value = c; o.textContent = c;
    companyEl.appendChild(o);
}});
ATS_LIST.forEach(a => {{
    const o = document.createElement('option');
    o.value = a; o.textContent = a;
    atsEl.appendChild(o);
}});

/* ---------- Helpers ---------- */
function esc(s) {{
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}}

/* Render Anomaly Warnings */
function renderWarnings() {{
    const wContainer = document.getElementById('anomalyWarnings');
    let html = '';
    
    // Check metadata for historical anomalies
    for (const [c, meta] of Object.entries(COMP_META)) {{
        if (meta.anomaly) {{
            html += `<div style="background:var(--warning-surface); color:var(--warning); padding:0.75rem; border-radius:var(--radius-sm); border:1px solid rgba(251,191,36,0.3); font-size:0.85rem; font-weight:500;">
                &#9888; <strong>${{esc(c)}}</strong>: ${{esc(meta.anomaly_reason)}} (Last Success: ${{esc(meta.last_success)}})
            </div>`;
        }}
    }}
    
    // Check current jobs for nav pollution
    const polluted = new Set();
    JOBS.forEach(j => {{
        if (j.invalid) polluted.add(j.company);
    }});
    
    polluted.forEach(c => {{
        html += `<div style="background:rgba(248,113,113,0.1); color:var(--danger); padding:0.75rem; border-radius:var(--radius-sm); border:1px solid rgba(248,113,113,0.3); font-size:0.85rem; font-weight:500;">
            &#9888; <strong>${{esc(c)}}</strong> Data quality issue - review (Nav/UI pollution detected in titles)
        </div>`;
    }});
    
    wContainer.innerHTML = html;
}}

function atsBadgeClass(src) {{
    const s = src.toLowerCase();
    if (s.includes('greenhouse')) return 'ats-greenhouse';
    if (s.includes('lever'))      return 'ats-lever';
    if (s.includes('workday'))    return 'ats-workday';
    if (s.includes('ashby'))      return 'ats-ashby';
    return 'ats-default';
}}

function renderRow(j) {{
    let titleHtml = esc(j.title);
    if (j.invalid) {{
        titleHtml = `<span style="color:var(--danger); font-weight:bold;" title="Possible UI pollution">&#9888;</span> ${{titleHtml}}`;
    }}
    return '<tr>' +
        '<td>' + esc(j.company) + '</td>' +
        '<td class="cell-title" title="' + esc(j.title) + '">' + titleHtml + '</td>' +
        '<td class="cell-location" title="' + esc(j.location) + '">' + esc(j.location) + '</td>' +
        '<td><span class="emp-pill">' + esc(j.employment_type || 'N/A') + '</span></td>' +
        '<td><span class="ats-badge ' + atsBadgeClass(j.ats_source) + '">' + esc(j.ats_source) + '</span></td>' +
        '<td>' + (j.apply_url
            ? '<a class="apply-btn" href="' + esc(j.apply_url) + '" target="_blank" rel="noopener">Apply <svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></a>'
            : '<span style="color:var(--text-muted)">—</span>') + '</td>' +
        '<td>' + esc(j.date_fetched) + '</td>' +
        '</tr>';
}}

/* ---------- State ---------- */
let sortCol = null;
let sortAsc = true;
let filtered = [...JOBS];

/* ---------- Filter + Render ---------- */
function applyFilters() {{
    const q   = searchEl.value.toLowerCase().trim();
    const cmp = companyEl.value;
    const ats = atsEl.value;

    const indiaOnly = indiaEl.checked;
    const highLpaOnly = highLpaEl.checked;

    filtered = JOBS.filter(j => {{
        if (cmp && j.company !== cmp) return false;
        if (ats && j.ats_source !== ats) return false;
        
        if (indiaOnly) {{
            const loc = (j.location || '').toLowerCase();
            // simple check for common india locations
            if (!loc.includes('india') && !loc.includes('bengaluru') && !loc.includes('bangalore') 
                && !loc.includes('hyderabad') && !loc.includes('pune') && !loc.includes('gurgaon')
                && !loc.includes('noida') && !loc.includes('chennai') && !loc.includes('mumbai') && !loc.includes('delhi')) {{
                return false;
            }}
        }}
        
        if (highLpaOnly) {{
            if (!HIGH_COMP_TARGETS.has(j.company)) return false;
        }}

        if (q) {{
            const hay = (j.company + ' ' + j.title + ' ' + j.location + ' '
                       + j.employment_type + ' ' + j.ats_source + ' '
                       + j.date_fetched + ' ' + j.departments).toLowerCase();
            if (!hay.includes(q)) return false;
        }}
        return true;
    }});

    if (sortCol) doSort(sortCol, false);
    render();
}}

function doSort(col, toggle) {{
    if (toggle) {{
        if (sortCol === col) {{ sortAsc = !sortAsc; }}
        else {{ sortCol = col; sortAsc = true; }}
    }}
    sortCol = col;

    filtered.sort((a, b) => {{
        let va = (a[col] || '').toLowerCase();
        let vb = (b[col] || '').toLowerCase();
        if (va < vb) return sortAsc ? -1 : 1;
        if (va > vb) return sortAsc ? 1 : -1;
        return 0;
    }});

    /* Update header indicators */
    tableEl.querySelectorAll('thead th').forEach(th => {{
        th.classList.remove('sort-active', 'sort-desc');
        if (th.dataset.col === col) {{
            th.classList.add('sort-active');
            if (!sortAsc) th.classList.add('sort-desc');
        }}
    }});
}}

function render() {{
    if (filtered.length === 0) {{
        tbody.innerHTML = '';
        emptyEl.style.display = '';
    }} else {{
        emptyEl.style.display = 'none';
        tbody.innerHTML = filtered.map(renderRow).join('');
    }}
    countEl.textContent = filtered.length;
}}

/* ---------- Events ---------- */
let debounceTimer;
searchEl.addEventListener('input', () => {{
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(applyFilters, 220);
}});
companyEl.addEventListener('change', applyFilters);
atsEl.addEventListener('change', applyFilters);
indiaEl.addEventListener('change', applyFilters);
highLpaEl.addEventListener('change', applyFilters);

tableEl.querySelectorAll('thead th').forEach(th => {{
    const col = th.dataset.col;
    if (!col || col === 'apply') return;
    th.addEventListener('click', () => {{ doSort(col, true); render(); }});
}});

/* ---------- Initial render ---------- */
renderWarnings();
render();

}})();
</script>
</body>
</html>"""

    # ------------------------------------------------------------------
    # Write to disk
    # ------------------------------------------------------------------
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html_content)


# ======================================================================
# Quick smoke-test when executed directly
# ======================================================================
if __name__ == "__main__":
    sample_jobs = [
        {
            "company": "Acme Corp",
            "title": "Senior Python Engineer",
            "location": "San Francisco, CA",
            "employment_type": "Full-time",
            "ats_source": "Greenhouse",
            "apply_url": "https://boards.greenhouse.io/acme/jobs/123",
            "date_fetched": "2026-07-11",
            "description": "<p>We are looking for a senior engineer…</p>",
            "departments": "Engineering",
        },
        {
            "company": "Globex Inc",
            "title": "Staff Frontend Developer",
            "location": "Remote",
            "employment_type": "Full-time",
            "ats_source": "Lever",
            "apply_url": "https://jobs.lever.co/globex/456",
            "date_fetched": "2026-07-10",
            "description": "<p>Join our design systems team…</p>",
            "departments": "Product, Design",
        },
        {
            "company": "Initech",
            "title": "Data Scientist",
            "location": "New York, NY",
            "employment_type": "Contract",
            "ats_source": "Workday",
            "apply_url": "https://initech.wd5.myworkdayjobs.com/789",
            "date_fetched": "2026-07-09",
            "description": "<p>Analyze large-scale data…</p>",
            "departments": "Data",
        },
        {
            "company": "Umbrella Ltd",
            "title": "DevOps Engineer",
            "location": "Austin, TX",
            "employment_type": "Full-time",
            "ats_source": "Ashby",
            "apply_url": "https://jobs.ashbyhq.com/umbrella/abc",
            "date_fetched": "2026-07-11",
            "description": "<p>Kubernetes, Terraform, CI/CD…</p>",
            "departments": "Infrastructure",
        },
    ]

    sample_custom = [
        {"name": "Wayne Enterprises", "careers_url": "https://wayneenterprises.com/careers"},
        {"name": "Stark Industries", "careers_url": "https://starkindustries.com/jobs"},
    ]

    out = "dashboard_preview.html"
    generate_dashboard(sample_jobs, out, sample_custom)
    print(f"[OK] Dashboard written to {out}")
