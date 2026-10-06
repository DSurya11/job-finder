"""Judge a job's pay against the floors in user_profile.yaml.

Verdicts, best to worst:
  target      stated pay meets your target (e.g. 12 LPA)
  ok          stated pay meets your minimum (e.g. 9 LPA)
  estimated   pay not stated; Claude's estimate meets your minimum
  unknown     pay not stated and not estimated
  low         stated (or estimated) pay is below your minimum
  unpaid      explicitly unpaid
  suspicious  asks the candidate for money, or similar scam markers

One floor applies to everything: an internship's monthly stipend is annualised
(stipend x 12) and held to the same minimum, so 9 LPA means 75,000 a month.
`min_stipend_per_month` in the profile overrides that for internships.
"""

from __future__ import annotations

import re

VERDICTS = ["target", "ok", "estimated", "unknown", "low", "unpaid", "suspicious"]
BAD = ("low", "unpaid", "suspicious")

_UNPAID = re.compile(
    r"\bunpaid\b|\bno stipend\b|stipend:\s*(?:nil|none|0\b|not provided|performance based only)|"
    r"\bvoluntary (?:position|role|internship)\b|\bwithout (?:pay|stipend|remuneration)\b",
    re.I,
)
# Legitimate employers do not charge candidates. Each phrase here is a request for
# money from the applicant, not a mention of fees the company handles for customers.
_SCAM = re.compile(
    r"registration fees?\b|security deposit|refundable deposit|training fees?\b|"
    r"enrol?lment fees?\b|course fees?\b|pay (?:a |the )?(?:fee|deposit|amount) (?:to|before|for) (?:join|start|apply|"
    r"training|onboard)|certificate fee|one[- ]time (?:joining |registration )?(?:fee|payment) "
    r"(?:of|is)|pay after placement|laptop deposit",
    re.I,
)
# Large employers warn candidates about exactly these scams ("we will never charge
# a registration fee"); a phrase preceded by such wording is not a red flag.
_DISCLAIMER = re.compile(
    r"\b(never|not|no|nor|without|don't|doesn't|won't|fraud\w*|scams?|beware|fake|"
    r"imperson\w+|unauthori[sz]ed)\b", re.I,
)


def floors(profile: dict) -> dict:
    prefs = (profile.get("raw") or {}).get("job_preferences") or {}
    return {
        "min_lpa": float(prefs.get("min_lpa", 9)),
        "target_lpa": float(prefs.get("target_lpa", 12)),
        "min_stipend": float(prefs.get("min_stipend_per_month")
                             or float(prefs.get("min_lpa", 9)) * 1e5 / 12),
        "target_stipend": float(prefs.get("target_lpa", 12)) * 1e5 / 12,
    }


def apply_band(job: dict) -> None:
    """Fill in a rough tier-table estimate when nothing better is known."""
    if job.get("salary_max_lpa") is not None or job.get("est_source") in ("claude", "ambitionbox"):
        return
    if job.get("est_source") == "market":
        from .paybands import estimate as tier
        if tier(job) is None:
            return                      # keep the market figure; there is no tier guess to prefer
    from .paybands import estimate
    band = estimate(job)
    job["est_min_lpa"], job["est_max_lpa"] = band if band else (None, None)
    job["est_source"] = "band" if band else None


def judge(job: dict, profile: dict) -> str:
    text = f"{job.get('title') or ''}\n{job.get('salary_text') or ''}\n{job.get('description') or ''}"
    # Only aggregator listings are screened: a tracked company's own board is not a
    # scam, and its postings mention deposits and fees as part of the actual work.
    if job.get("source") in ("linkedin", "internshala") and any(
        not _DISCLAIMER.search(text[max(0, m.start() - 160): m.start()])
        for m in _SCAM.finditer(text)
    ):
        return "suspicious"

    f = floors(profile)
    intern = job.get("employment_type") == "Internship" or job.get("level") == "Intern"
    # An internship listing that quotes an annual figure is quoting the salary of the
    # job it converts to, so it is held to the annual floor, not the stipend floor.
    if intern and job.get("salary_max_lpa") is not None and not re.search(
        r"month|stipend|week|/\s*mo\b", job.get("salary_text") or "", re.I
    ):
        intern = False
    # Annual floors, or the stipend floor expressed as LPA for internships.
    low_bar = f["min_stipend"] * 12 / 1e5 if intern else f["min_lpa"]
    high_bar = max(low_bar, f["target_stipend"] * 12 / 1e5) if intern else f["target_lpa"]

    top = job.get("salary_max_lpa")
    if top is not None:
        if top >= high_bar:
            return "target"
        return "ok" if top >= low_bar else "low"
    if _UNPAID.search(text):
        return "unpaid"

    if job.get("est_max_lpa") is not None and job.get("est_source") != "market":
        # A market-wide average says nothing about this company, so it is shown but
        # never used to hide a job. Judge an estimated range by its middle: a 6-14 LPA range mostly pays under 9.
        middle = ((job.get("est_min_lpa") or job["est_max_lpa"]) + job["est_max_lpa"]) / 2
        return "estimated" if middle >= low_bar else "low"
    if job.get("brain_flag") in ("unpaid", "suspicious"):
        return job["brain_flag"]
    return "unknown"
