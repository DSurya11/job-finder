# Job Finder — Apify-powered India Internship Scraper

Scrapes LinkedIn Jobs, LinkedIn Posts, Indeed India, and Glassdoor via **Apify APIs**, filters for India-based paid internships matching your profile, exports a formatted **Excel file**, and generates a ready-to-paste **Claude AI prompt** for intelligent scoring.

## Files

| File | Purpose |
|------|---------|
| `job_finder.py` | Main scraper — calls Apify actors, filters, exports Excel |
| `user_profile.yaml` | **Fill this in** — your personal/professional details and search config |
| `.env` | Your secrets (gitignored) — copy from `.env.example` |
| `.env.example` | Template for the `.env` file |
| `requirements.txt` | Python dependencies |

Generated at runtime:
- `jobs.xlsx` — formatted job listings ready to upload to Claude AI
- `jobs_claude_prompt.txt` — paste this into Claude.ai

## Setup

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Get an Apify API token

1. Sign up / log in at <https://console.apify.com>
2. Go to **Settings → Integrations** and copy your **Personal API Token**
3. Create a `.env` file in this directory:

```text
APIFY_TOKEN=your_token_here
```

### 3. Fill in your profile

Open `user_profile.yaml` and fill in your details:
- Personal info, education, skills, experience, projects
- `resume_path` — path to your resume PDF
- `job_preferences` — roles, locations, exclude keywords
- `search.keywords` — what to search for on each job board
- `apify_actors` — enable/disable sources, verify actor IDs

> **Verify actor IDs** before running — search <https://console.apify.com/store> to confirm they are still published and check their input schemas.

## Run

```powershell
python job_finder.py
```

Override profile or output path:

```powershell
python job_finder.py --profile user_profile.yaml --resume "path\to\resume.pdf" --output jobs.xlsx
```

## Scoring with Claude AI

The script does **not** score jobs automatically. Instead it exports a clean Excel file and generates a prompt that you paste into Claude.ai for superior, context-aware scoring.

After `job_finder.py` finishes:

1. Open <https://claude.ai>
2. Attach `jobs.xlsx`
3. Attach your resume PDF
4. Paste the contents of `jobs_claude_prompt.txt`

Claude will filter, score, and tier the results into Apply Today / Strong Match / Bulk Apply cards with direct URLs.

## Sources

| Source | What is scraped |
|--------|----------------|
| LinkedIn Jobs | Standard job listings searched by keyword + India location |
| LinkedIn Posts | Hiring posts (`"hiring <role> India"`) from the LinkedIn feed |
| Indeed India | `in.indeed.com` — keyword + country=in |
| Glassdoor | Glassdoor job listings for India |
| Naukri | Optional — set `enabled: true` and add an actor ID in `user_profile.yaml` |

## Configuration Reference

All configuration lives in `user_profile.yaml`. Environment variables in `.env`:

```text
APIFY_TOKEN=          # required
OUTPUT_EXCEL=jobs.xlsx
RESUME_PATH=          # optional override for resume path
```