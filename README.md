# Job Finder

Pulls open jobs in India straight from company job boards, works out the role, level, experience, salary and city for each one, scores them against your profile, and gives you a web app to filter, shortlist and track applications.

It reads three kinds of source:

- **Company job boards** (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday, TurboHire): about 250 companies, fetched in full, linking straight to the real application page.
- **Big-company career sites** with their own format: Google, Microsoft, Apple, Meta, Amazon, Uber, Goldman Sachs, Atlassian and a few more.
- **Aggregators**: LinkedIn's public job search and Internshala, for jobs at companies not in the list. A job already found on a company's own board is not duplicated.

## Quick start

```bash
make up          # sets up anything missing, builds the web app, starts the server
make refresh     # fetch jobs from every source (first run takes about 30 min)
make down        # stop the server
```

`make up` prints the address (http://127.0.0.1:8000 by default; `make up PORT=8123` to change it). It creates the Python environment, installs packages and rebuilds the web app only when something changed, so running it again is quick. `make down` always succeeds, whether or not the server was running. Also: `make status`, `make logs`, `make restart`, `make pay`, `make test`.

Meta and DE Shaw are read with a real browser; install it once with `.venv/bin/playwright install chromium`.

After the first run, the **Refresh** button in the app does the same fetch.

To refresh every morning at 7:00, add this to `crontab -e`:

```
0 7 * * * cd /path/to/job-finder && .venv/bin/python -m jobfinder run >> data/run.log 2>&1
```

## Using the app

- **Left rail** — views with counts: All, New today, Shortlisted, Applied, Interview, Offer, Rejected, and Coverage.
- **Table** — one 36px row per job: fit score, company, title, location, pay, posted, source, status. Click Fit, Company, Pay or Posted to sort. The bar under the table sets rows per page (25, 50, 100 or 200, remembered) and has First, Previous, Next and Last; `n` and `p` also change page. The same title at the same company and level is shown once with a count (`×4`); the job card lists the other postings.
- **Top bar** — search (title, company and place, matching from the start of a word) and filter menus: Level, Role, City, Pay, Posted, Company, More.
- **Job card** — click a row and the card unfolds out of it, centred over the table: the description laid out with its section headings and bullet lists, the reasons behind the fit score, where the pay figure comes from, the Apply link, status buttons and notes. `esc` or a click outside closes it; `j` / `k` step to the next job with the card open.
- **Coverage** — one row per company with what the last run returned. Anything that failed, came back empty, or dropped sharply against the previous run is flagged.
- **Copy Claude prompt** — press `c` on a few jobs and the bar at the bottom copies a prompt with your profile and those descriptions.

Motion comes from open component libraries (Magic UI's number ticker and blur fade, Motion Primitives' animated background), adapted in `web/src/fx/`. The job card's open and close (`web/src/Inspector.tsx`) follow the story inspector in the tachyon-news project. It animates transform and opacity only and respects the system's reduced-motion setting.

Keyboard: `j` / `k` move, `o` opens the posting, `s` shortlists, `a` marks applied, `x` dismisses, `c` selects for the Claude prompt, `/` searches, `?` lists these.

## Pay checks

Every job gets a pay verdict against the floors in `user_profile.yaml` (`min_lpa: 9`, `target_lpa: 12`; an internship's stipend is annualised and held to the same floor, so 75,000 a month, unless you set `min_stipend_per_month`):

| Verdict | Meaning |
|---|---|
| Meets target / minimum | The posting states pay at or above your floor |
| Below minimum | Stated pay is under your floor |
| Unpaid | The posting says it is unpaid or has no stipend |
| Looks fake | An aggregator listing that asks the candidate for a fee or deposit |
| Estimate meets minimum | Pay not stated; the estimate reaches your floor |
| Not stated | No pay in the posting and no basis for an estimate |

Low-pay, unpaid and fake listings are hidden by default; the **Hide low-pay, unpaid and fake** switch shows them again.

### When the posting does not state pay

Most postings in India do not, so the app fills in a figure and always marks it. In order of preference:

1. **AmbitionBox (`est`).** Reported salaries for that designation at that company, for the experience the job asks for. The job card shows the average, how many salaries it is based on, and a link to the page.

   ```bash
   .venv/bin/python -m jobfinder pay --limit 300      # salary pages to request this run
   ```

   Lookups are cached, so each company and designation is requested once, and later fetches reuse them. Small samples (one or two salaries) are shown as such; treat them with care.
2. **Claude (`est`, needs an API key).** For jobs AmbitionBox has no page for, Claude estimates the range and flags unpaid or scam-like listings.

   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...             # from https://console.anthropic.com
   .venv/bin/python -m jobfinder brain --limit 300
   ```
3. **Market average (`mkt`).** For a company AmbitionBox has no page for and that is not in the tier list, the India-wide average for that role and experience across all companies. It is shown for reference only and never hides a job, because it says nothing about that particular company.
4. **Pay tier (`guess`).** A fallback from `jobfinder/paybands.py`: five company tiers with one range per level. It is the same for every role at a company and level, so use it only as a ballpark.

A job is hidden as low pay when its stated pay, or the top of its estimate, is under your minimum.

## Your profile

Matching uses `user_profile.yaml`. The fields that affect the score:

| Field | Effect |
|---|---|
| `skills.primary`, `secondary`, `ml_ai` | Skills found in the title or description (primary counts double) |
| `job_preferences.type` | `internship` targets Intern roles, `full-time` targets Entry |
| `job_preferences.levels` | Optional override, e.g. `[Intern, Entry]` to target both |
| `job_preferences.roles` | Mapped to role families (Backend, Full Stack, ML / AI, …) |
| `job_preferences.preferred_locations` | Cities, `Remote`, or `India` |
| `job_preferences.exclude_keywords` | Words in a title that pull the score down |

After editing it, run `.venv/bin/python -m jobfinder rescore`.

## Adding companies

`companies.yaml` is the list that gets fetched. To add companies, put their names in `seeds.txt` and run:

```bash
.venv/bin/python -m jobfinder discover seeds.txt --write
```

This tries each name against every public job-board API and adds the ones that list India jobs. Names it cannot place stay in `seeds.txt` and are retried next time. If a guessed name does not work, add the board's slug after a pipe (`Razorpay | razorpaysoftwareprivatelimited`).

Workday companies need three values from their careers URL, `https://{tenant}.{wd_instance}.myworkdayjobs.com/{site}`:

```yaml
- name: Adobe
  ats: workday
  tenant: adobe
  wd_instance: wd5
  site: external_experienced
```

## LinkedIn

LinkedIn is read through its public, logged-out job search only. No account, login or cookies are involved, so your own LinkedIn account is never at risk. LinkedIn's user agreement still prohibits automated collection, and it throttles aggressively, so this source:

- searches a fixed list of keywords for India, limited to the last 7 days,
- makes about one request a second, and
- fetches full descriptions for only the 400 best-scoring new jobs per run.

Edit the entry in `companies.yaml` to change `keywords`, `max_pages` or `posted_within` (`r86400` is 24 hours), or set `enabled: false` to turn it off.

## What it does not cover

- **Naukri** requires a captcha for every search, so it is not scraped.
- **Sites behind bot protection or with no listings page.** Citadel Securities sits behind a Cloudflare challenge; Zomato (Eternal) hires by email; Walmart, SAP, Zerodha and American Express need bespoke work. These are `ats: custom` and appear under *manual* on the Coverage tab with a link to check by hand.
- **Companies not in `companies.yaml`.** LinkedIn and Internshala catch many of them, but only for the configured keywords.
- **Salary**, for most jobs. It is shown only when the posting states it, which few India postings do. Internshala stipends are the main exception.

## Commands

| Command | What it does |
|---|---|
| `python -m jobfinder run` | Fetch all companies, then fetch missing descriptions |
| `python -m jobfinder run --only greenhouse,Stripe` | Fetch only some boards or companies |
| `python -m jobfinder run --no-details` | Skip the description pass (about 4 minutes) |
| `python -m jobfinder serve --port 8000` | Start the web app |
| `python -m jobfinder discover seeds.txt --write` | Find job boards for new companies |
| `python -m jobfinder pay --limit 300` | Look up pay on AmbitionBox for jobs that do not state it |
| `python -m jobfinder brain --limit 300` | Have Claude estimate pay and flag fake listings (needs an API key) |
| `python -m jobfinder rescore` | Re-score stored jobs after a profile change |
| `python -m jobfinder health` | Print companies whose last fetch looks wrong |
| `python -m pytest tests` | Run the parser tests |

## Layout

```
jobfinder/
  sources.py    one adapter per job board
  feeds.py      career sites with their own format, LinkedIn, Internshala
  enrich.py     location, salary, experience, role and level parsing
  details.py    second pass that fetches full descriptions
  pipeline.py   fetch, store, health tracking
  score.py      match score against user_profile.yaml
  pay.py        pay verdict against your salary floors
  portal.py     AmbitionBox pay lookup, cached per company and designation
  paybands.py   fallback pay ranges by company tier and level
  brain.py      Claude pay estimates and fake-listing flags
  discover.py   find a company's job board
  server.py     API for the web app
  db.py         SQLite store (data/jobs.db)
fetchers/       company-specific scrapers (Amazon, Goldman Sachs, Swiggy, …)
web/            React app (Vite, Tailwind, Motion)
```

For frontend work, run `npm run dev` in `web/` alongside `python -m jobfinder serve`; the dev server proxies `/api` to port 8000.
