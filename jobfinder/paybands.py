"""Rough pay bands for jobs that do not state their pay.

These are typical India ranges by company tier and seniority, written from
general knowledge of what such companies pay. They are NOT taken from the
posting and are NOT live data from a salary site; the app always labels them
as rough estimates. `python -m jobfinder brain` replaces them with a per-job
estimate from Claude when an API key is configured.

All figures are total annual pay in lakhs (LPA). Internship figures are the
monthly stipend times twelve.
"""

from __future__ import annotations

import re

# tier -> level -> (low, high)
BANDS: dict[str, dict[str, tuple[float, float]]] = {
    # Trading firms and frontier AI labs
    "S": {"Intern": (15, 36), "Entry": (30, 65), "Unspecified": (35, 80), "Mid": (45, 95),
          "Senior": (70, 150), "Staff+": (110, 250), "Manager": (90, 200)},
    # Top-paying product companies
    "A": {"Intern": (9, 18), "Entry": (20, 45), "Unspecified": (24, 55), "Mid": (30, 60),
          "Senior": (50, 100), "Staff+": (80, 180), "Manager": (70, 150)},
    # Strong product companies, well-funded startups, banks' technology arms
    "B": {"Intern": (4.8, 10), "Entry": (12, 25), "Unspecified": (15, 32), "Mid": (20, 40),
          "Senior": (35, 65), "Staff+": (55, 110), "Manager": (45, 95)},
    # Large multinationals' India centres, hardware, industrial, mid-size startups
    "C": {"Intern": (2.4, 6), "Entry": (6, 14), "Unspecified": (9, 20), "Mid": (12, 24),
          "Senior": (20, 40), "Staff+": (35, 65), "Manager": (28, 60)},
    # IT services, consulting delivery, back-office operations
    "D": {"Intern": (1.2, 3.6), "Entry": (3.5, 8), "Unspecified": (5, 12), "Mid": (7, 15),
          "Senior": (14, 28), "Staff+": (25, 45), "Manager": (18, 40)},
}

_TIERS = {
    "S": """Tower Research, Hudson River Trading, Jump Trading, IMC Trading, Graviton Research,
        Squarepoint, WorldQuant, Optiver, Citadel Securities, DE Shaw, OpenAI, Anthropic""",
    "A": """Google, Microsoft, Apple, Meta, Amazon, Uber, Atlassian, Stripe, Databricks, Snowflake,
        Rubrik, NVIDIA, Adobe, Salesforce, Airbnb, Coinbase, Figma, Notion, Confluent, Cohesity,
        Palo Alto Networks, Roblox, Snap, Glean, Cursor, Harvey, Scale AI, Wiz, Datadog,
        Cloudflare, Goldman Sachs, Flipkart, ServiceNow, Waymo, ElevenLabs, Together AI,
        Pure Storage, Tekion, Sprinklr, Intuit""",
    "B": """Razorpay, CRED, Meesho, Groww, PhonePe, Swiggy, Zomato, InMobi, Glance, Zerodha,
        MongoDB, Elastic, Twilio, Okta, GitLab, Zscaler, Netskope, CrowdStrike, Arista Networks,
        Druva, Commvault, Fivetran, ClickHouse, Redis, Kong, Cockroach Labs, SingleStore,
        Yugabyte, Starburst, Grafana Labs, New Relic, Sumo Logic, Amplitude, Mixpanel, Vercel,
        Morgan Stanley, JPMorgan Chase, American Express, Visa, Mastercard, PayPal, BlackRock,
        Walmart Global Tech, Target, Lowe's India, Cisco, Intel, Broadcom, Marvell, Cadence,
        Samsung R&D, Autodesk, Workday, Zoom, Expedia, eBay, Agoda, Grab, Wise, Tide, Airwallex,
        Adyen, Toast, Flexport, Samsara, Motive, Roku, Navan, Coupa, Anaplan, Smartsheet,
        Zendesk, Freshworks, Zeta, Atlan, Mindtickle, Whatfix, Zenoti, Observe.AI, Sarvam AI,
        Hevo Data, HackerRank, Fi Money, Paytm, Upstox, Astera Labs, Analog Devices, KLA,
        Applied Materials, Capital One, Nasdaq, LSEG, Fidelity, Wells Fargo, Truecaller,
        Skyflow, Canva, Red Hat, F5, Equinix, Guidewire, Yahoo, Etsy, Sabre, Coursera, Zuora,
        Outreach, Salesloft, ZoomInfo, Fastly, Poshmark, Scopely, Warner Bros Discovery,
        Disney, athenahealth, Western Digital, Micron, NXP, Unacademy""",
    "C": """HPE, HP, Citi, Barclays, Deutsche Bank, State Street, Northern Trust, Morningstar,
        S&P Global, Broadridge, Invesco, Thomson Reuters, Philips, GE HealthCare, GE Vernova,
        GE Aerospace, Medtronic, Stryker, Bosch, Continental, Airbus, Boeing, Rolls-Royce,
        Shell, bp, Maersk, Caterpillar, 3M, Abbott, Novartis, AstraZeneca, Pfizer, Mondelez,
        Nike, Gap, Gartner, Rakuten, Trimble, PTC, Rockwell Automation, Carrier, Baker Hughes,
        ABB, Agilent, Illumina, Thermo Fisher, Danaher, Harman, Aptiv, GM, Stellantis, Sony,
        T-Mobile, Verizon, AT&T, Motorola Solutions, FIS, Fiserv, Sixt, Thoughtworks,
        Bazaarvoice, Model N, Zinnia, Netradyne, Sigmoid, ixigo, Cars24, NoBroker, Scaler,
        Turing, Pocket FM, Fampay, Bureau, Kredx, Lendingkart, Tamara, Apna, Freshprints,
        Newton School, Interview Kickstart, Entropik, LogiNext, CynLr, Smallest AI, Lokal, Ola,
        SAP Labs India""",
    "D": "PwC, Kyndryl, DXC, Cognizant, Hitachi",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


TIER_OF = {_norm(name): tier for tier, names in _TIERS.items() for name in names.split(",")}


def estimate(job: dict) -> tuple[float, float] | None:
    """(low, high) LPA for a job at a tiered company, or None if we cannot say."""
    tier = TIER_OF.get(_norm(job.get("company") or ""))
    if not tier:
        return None
    low, high = BANDS[tier].get(job.get("level") or "Unspecified", BANDS[tier]["Unspecified"])
    if not job.get("is_tech"):
        # Non-engineering roles at the same company and level pay noticeably less.
        low, high = low * 0.55, high * 0.65
    return round(low, 1), round(high, 1)
