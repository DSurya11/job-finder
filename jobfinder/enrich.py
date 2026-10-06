"""Turn a raw posting into filterable fields.

Everything here is deterministic text parsing: India/remote detection,
salary, years of experience, role family, seniority and employment type.
"""

from __future__ import annotations

import html
import re

# ── Text helpers ─────────────────────────────────────────────────────────────

_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</(p|div|li|h[1-6]|ul|ol|tr|section)>|<br\s*/?>", re.I)
_LI = re.compile(r"<li[^>]*>", re.I)
_HEADING = re.compile(r"<(h[1-6])[^>]*>(.*?)</\1>", re.I | re.S)
_BOLD_LINE = re.compile(
    r"<(?:p|div)[^>]*>\s*<(?:strong|b)[^>]*>([^<]{3,70})</(?:strong|b)>\s*:?\s*(?:<br\s*/?>)?\s*</(?:p|div)>",
    re.I,
)
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n\s*\n+")


def html_to_text(raw: str | None, limit: int = 20000) -> str:
    """HTML (possibly entity-escaped, as Greenhouse returns it) to plain text."""
    if not raw:
        return ""
    text = raw
    if "&lt;" in text:
        text = html.unescape(text)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    # Headings, and paragraphs that are only bold text, are marked so the app can
    # show them as section titles.
    text = _HEADING.sub(lambda m: f"\n## {_TAG.sub(' ', m.group(2)).strip()}\n", text)
    text = _BOLD_LINE.sub(lambda m: f"\n## {_TAG.sub(' ', m.group(1)).strip()}\n", text)
    text = _LI.sub("\n• ", text)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"^## *$", "", text, flags=re.M)        # an empty heading tag
    text = _NL.sub("\n\n", text).strip()
    return text[:limit]


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def iso_date(value) -> str:
    """YYYY-MM-DD if the value starts with one, else empty. Some sites send 'Mon Oct 05'."""
    text = str(value or "")
    return text[:10] if _ISO_DATE.match(text) else ""


# ── Location ─────────────────────────────────────────────────────────────────

# canonical city -> aliases (lowercase)
_CITY_ALIASES: dict[str, tuple[str, ...]] = {
    "Bengaluru": ("bengaluru", "bangalore", "bengalore"),
    "Hyderabad": ("hyderabad", "secunderabad"),
    "Pune": ("pune",),
    "Mumbai": ("mumbai", "navi mumbai", "thane", "bombay"),
    "Delhi NCR": ("delhi", "new delhi", "gurgaon", "gurugram", "noida",
                  "greater noida", "faridabad", "ghaziabad", "ncr"),
    "Chennai": ("chennai", "madras"),
    "Kolkata": ("kolkata", "calcutta"),
    "Ahmedabad": ("ahmedabad", "gandhinagar", "gift city"),
    "Jaipur": ("jaipur",),
    "Kochi": ("kochi", "cochin", "ernakulam"),
    "Thiruvananthapuram": ("thiruvananthapuram", "trivandrum"),
    "Coimbatore": ("coimbatore",),
    "Indore": ("indore",),
    "Chandigarh": ("chandigarh", "mohali", "panchkula"),
    "Bhubaneswar": ("bhubaneswar", "bhubaneshwar"),
    "Nagpur": ("nagpur",),
    "Lucknow": ("lucknow",),
    "Vadodara": ("vadodara", "baroda"),
    "Surat": ("surat",),
    "Visakhapatnam": ("visakhapatnam", "vizag"),
    "Mysuru": ("mysuru", "mysore"),
    "Mangaluru": ("mangaluru", "mangalore"),
    "Goa": ("goa", "panaji"),
    "Bhopal": ("bhopal",),
    "Vijayawada": ("vijayawada",),
    "Madurai": ("madurai",),
    "Guwahati": ("guwahati",),
    "Patna": ("patna",),
    "Dehradun": ("dehradun",),
    "Jabalpur": ("jabalpur",),
}
_ALIAS_TO_CITY = {a: c for c, al in _CITY_ALIASES.items() for a in al}
_CITY_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, _ALIAS_TO_CITY), key=len, reverse=True)) + r")\b",
    re.I,
)
_STATE_RE = re.compile(
    r"\b(karnataka|maharashtra|telangana|tamil ?nadu|haryana|uttar pradesh|kerala|"
    r"gujarat|west bengal|andhra pradesh|rajasthan|madhya pradesh|punjab|odisha)\b",
    re.I,
)
_INDIA_RE = re.compile(r"\bindia\b", re.I)
# Amazon-style "IN, KA, Bengaluru" / "IN-Bangalore". A trailing ", IN" is Indiana.
_IN_PREFIX_RE = re.compile(r"(?:^|[;|/]\s*)IN\s*[,\-]")
_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere|distributed)\b", re.I)
_GLOBAL_FILLER = re.compile(
    r"\b(remote|work from home|wfh|anywhere|distributed|global|worldwide|world|"
    r"apac|asia|asia pacific|hybrid|flexible|location|first|friendly|fully|only|or|and)\b",
    re.I,
)
MULTI_LOCATION_RE = re.compile(r"^\s*\d+\s+locations?\s*$", re.I)


def locate(location: str | None) -> dict:
    """Classify a location string.

    Returns {"in_india", "cities", "remote", "scope"} where scope is one of
    "india", "remote_global", "unknown" (needs the detail page), "abroad".
    """
    loc = (location or "").strip()
    cities = []
    for m in _CITY_RE.finditer(loc):
        city = _ALIAS_TO_CITY[m.group(1).lower()]
        if city not in cities:
            cities.append(city)
    remote = bool(_REMOTE_RE.search(loc))
    india = bool(
        cities or _INDIA_RE.search(loc) or _STATE_RE.search(loc) or _IN_PREFIX_RE.search(loc)
    )
    if india:
        scope = "india"
    elif not loc or MULTI_LOCATION_RE.match(loc):
        scope = "unknown"
    elif remote and not re.sub(r"[\W_]+", "", _GLOBAL_FILLER.sub("", loc)):
        scope = "remote_global"
    else:
        scope = "abroad"
    return {"in_india": india, "cities": cities, "remote": remote, "scope": scope}


# ── Salary ───────────────────────────────────────────────────────────────────

_NUM = r"(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)"
_SEP = r"\s*(?:-|–|—|to|and)\s*"
_LAKH_UNIT = r"(?:lpa|l\.p\.a\.?|lakhs?|lacs?|lac)"
_LPA_RANGE = re.compile(rf"{_NUM}{_SEP}{_NUM}\s*{_LAKH_UNIT}\b", re.I)
_LPA_SINGLE = re.compile(rf"{_NUM}\s*{_LAKH_UNIT}\b", re.I)
_INR_AMOUNT = re.compile(
    rf"(?:₹|\brs\.?|\binr)\s*{_NUM}\s*(k|lakhs?|lacs?|lpa|cr|crores?)?"
    rf"(?:{_SEP}(?:₹|rs\.?|inr)?\s*{_NUM}\s*(k|lakhs?|lacs?|lpa|cr|crores?)?)?",
    re.I,
)
_USD_RANGE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?"
    r"(?:\s*(?:-|–|—|to)\s*\$?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?)?",
    re.I,
)
_MONTHLY = re.compile(r"(per month|/\s*month|\bp\.?m\.?\b|monthly|/\s*mo\b|a month|stipend)", re.I)
_PAY_CONTEXT = re.compile(
    r"(ctc|salary|compensation|stipend|package|pay range|pay band|remuneration|"
    r"per annum|p\.a\.|annual|lpa|₹|inr)",
    re.I,
)


def _f(num: str) -> float:
    return float(num.replace(",", ""))


def _inr_to_lpa(value: float, unit: str | None, monthly: bool) -> float | None:
    unit = (unit or "").lower()
    if unit.startswith(("lakh", "lac", "lpa")):
        rupees = value * 1e5
    elif unit.startswith("cr"):
        rupees = value * 1e7
    elif unit == "k":
        rupees = value * 1e3
    else:
        rupees = value
    if monthly:
        rupees *= 12
    lpa = rupees / 1e5
    # Anything outside this band is almost certainly not an annual salary.
    return round(lpa, 2) if 0.3 <= lpa <= 500 else None


def parse_salary(text: str | None, struct: dict | None = None) -> dict:
    """Find pay in free text or an ATS-supplied structure.

    Returns {"min_lpa", "max_lpa", "text"}; LPA is only set for INR amounts so
    a US pay band on a global posting never masquerades as an India salary.
    """
    out = {"min_lpa": None, "max_lpa": None, "text": ""}

    if struct and (struct.get("min") or struct.get("max")):
        lo = struct.get("min") or struct.get("max")
        hi = struct.get("max") or lo
        cur = (struct.get("currency") or "").upper()
        interval = (struct.get("interval") or "year").lower()
        out["text"] = f"{cur} {lo:,.0f}–{hi:,.0f} / {interval}".strip()
        if cur == "INR":
            monthly = "month" in interval
            out["min_lpa"] = _inr_to_lpa(float(lo), None, monthly)
            out["max_lpa"] = _inr_to_lpa(float(hi), None, monthly)
        return out
    if struct and struct.get("text"):
        out["text"] = str(struct["text"])[:160]
        text = f"{struct['text']}\n{text or ''}"

    if not text:
        return out

    def near(m: re.Match, pattern: re.Pattern, before: int = 80, after: int = 40) -> bool:
        return bool(pattern.search(text[max(0, m.start() - before): m.end() + after]))

    for m in _LPA_RANGE.finditer(text):
        lo, hi = _f(m.group(1)), _f(m.group(2))
        if lo <= hi <= 500 and near(m, _PAY_CONTEXT):
            out.update(min_lpa=lo, max_lpa=hi, text=out["text"] or m.group(0).strip())
            return out
    for m in _LPA_SINGLE.finditer(text):
        val = _f(m.group(1))
        if 0.5 <= val <= 500 and near(m, _PAY_CONTEXT):
            out.update(min_lpa=val, max_lpa=val, text=out["text"] or m.group(0).strip())
            return out
    for m in _INR_AMOUNT.finditer(text):
        monthly = near(m, _MONTHLY, before=40, after=30)
        unit1, unit2 = m.group(2), m.group(4)
        lo = _inr_to_lpa(_f(m.group(1)), unit1 or unit2, monthly)
        hi = _inr_to_lpa(_f(m.group(3)), unit2 or unit1, monthly) if m.group(3) else lo
        if lo and hi and lo <= hi:
            snippet = m.group(0).strip() + (" / month" if monthly else "")
            out.update(min_lpa=lo, max_lpa=hi, text=out["text"] or snippet)
            return out
    if not out["text"]:
        for m in _USD_RANGE.finditer(text):
            lo = _f(m.group(1)) * (1000 if m.group(2) else 1)
            if lo >= 1000 and near(m, _PAY_CONTEXT, before=120, after=60):
                out["text"] = re.sub(r"\s+", " ", m.group(0)).strip() + " (USD)"
                break
    return out


# ── Experience ───────────────────────────────────────────────────────────────

_EXP_RANGE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I
)
_EXP_SINGLE = re.compile(r"(\d{1,2})\s*(\+|plus)?\s*(?:years?|yrs?)", re.I)
_EXP_CONTEXT = re.compile(r"(experience|exp\b|industry|professional|hands[- ]on|working)", re.I)
_FRESHER = re.compile(
    r"\b(freshers?|fresh graduates?|recent graduates?|new grads?|no (?:prior )?experience|"
    r"0\s*-\s*\d\s*(?:years?|yrs?)|final[- ]year students?|currently (?:enrolled|pursuing)|"
    r"graduating in|class of 20\d\d|batch of 20\d\d|20\d\d (?:batch|graduates?|passouts?))\b",
    re.I,
)


def parse_experience(text: str | None) -> tuple[float | None, float | None]:
    """Years of experience asked for, as (min, max). First mention wins."""
    if not text:
        return None, None
    found: list[tuple[int, float, float | None]] = []
    for m in _EXP_RANGE.finditer(text):
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo <= hi <= 30:
            found.append((m.start(), lo, hi))
    for m in _EXP_SINGLE.finditer(text):
        val = float(m.group(1))
        window = text[max(0, m.start() - 60): m.end() + 60]
        if val <= 25 and _EXP_CONTEXT.search(window):
            if not any(abs(pos - m.start()) < 12 for pos, _, _ in found):
                found.append((m.start(), val, None))
    if found:
        _, lo, hi = min(found)
        return lo, hi
    if _FRESHER.search(text):
        return 0.0, 1.0
    return None, None


# ── Role family, seniority, employment type ──────────────────────────────────

_ROLE_RULES: list[tuple[str, bool, re.Pattern]] = [
    (name, tech, re.compile(pattern, re.I))
    for name, tech, pattern in [
        ("ML / AI", True, r"machine learning|\bml\b|\bai\b|deep learning|\bnlp\b|computer vision|"
                          r"\bllm|gen ?ai|applied scientist|research scientist|research engineer|mlops"),
        ("Data Science", True, r"data scien|decision scien|quantitative research|\bquant\b|statistician"),
        ("Data Engineering", True, r"data engineer|analytics engineer|\betl\b|data platform|big data|"
                                   r"data warehouse|database engineer|\bdba\b"),
        ("Data Analyst", True, r"data analyst|business analyst|bi (developer|engineer|analyst)|"
                               r"business intelligence|product analyst|analytics"),
        ("Embedded / Hardware", True, r"embedded|firmware|\bvlsi\b|\basic\b|\bfpga\b|\brtl\b|hardware|"
                                      r"design verification|physical design|\bsoc design|silicon|"
                                      r"\bdft\b|analog|circuit|\bcad\b engineer|electrical engineer"),
        ("Security", True, r"security|appsec|infosec|penetration|soc analyst|threat|vulnerab|cryptograph"),
        ("DevOps / SRE", True, r"devops|\bsre\b|site reliability|platform engineer|infrastructure|"
                               r"cloud engineer|kubernetes|release engineer|build engineer|"
                               r"systems? engineer|network engineer|production engineer"),
        ("QA / SDET", True, r"\bqa\b|\bsdet\b|quality (assurance|engineer)|test (engineer|automation)|"
                            r"software engineer in test|automation engineer|tester"),
        ("Mobile", True, r"android|\bios\b|mobile|flutter|react native|kotlin|swift"),
        ("Frontend", True, r"front[- ]?end|\bui (engineer|developer)|web developer|react(\.?js)? developer|"
                           r"angular|javascript (engineer|developer)"),
        ("Full Stack", True, r"full[- ]?stack|\bmern\b|\bmean\b"),
        ("Backend", True, r"back[- ]?end|server[- ]side|api (engineer|developer)|"
                          r"(python|java|golang|go|node(\.?js)?|\.net|c\+\+|ruby|scala|rust) "
                          r"(engineer|developer)|distributed systems"),
        ("Support", False, r"support|customer success|technical account|helpdesk|service desk"),
        ("Sales / Marketing", False, r"sales|account executive|marketing|business development|\bbdr\b|"
                                     r"\bsdr\b|growth|partnership|account manager|pre[- ]?sales"),
        ("Software Engineering", True, r"software|\bsde\b|\bswe\b|\bsdet?\b|developer|programmer|"
                                       r"member of technical staff|\bmts\b|technical staff|"
                                       r"engineer(ing)? intern|technology (analyst|associate|intern)|"
                                       r"solutions? (engineer|architect)|application engineer|"
                                       r"technical architect|engineering manager|\bengineer\b"),
        ("Product", False, r"product manager|product owner|program manager|\bapm\b|\btpm\b|"
                           r"product management|project manager|scrum master"),
        ("Design", False, r"designer|\bux\b|\bui/ux\b|user research|design"),
        ("Finance / Ops / HR", False, r"finance|accountant|accounting|\bhr\b|human resources|recruit|"
                                      r"talent|operations|legal|counsel|compliance|payroll|"
                                      r"procurement|supply chain|\badmin\b|audit|\btax\b|\brisk\b"),
    ]
]

_INTERN_RE = re.compile(r"\b(intern|internship|interns|co-?op|summer analyst|apprentice)\b", re.I)
_GET_RE = re.compile(r"graduate engineer trainee|management trainee", re.I)
_MANAGER_RE = re.compile(
    r"\b(manager|director|head of|vp|vice president|chief|president|general manager)\b", re.I
)
_STAFF_RE = re.compile(
    r"\b(staff|principal|distinguished|fellow|architect|lead|sde[- ]?(iv|4)|"
    r"(engineer|developer|scientist) (iv|v|4|5))\b",
    re.I,
)
_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|sde[- ]?(iii|3)|smts|(engineer|developer|scientist|analyst) (iii|3)|"
    r"mts[- ]?(iii|3|iv|4)|l[5-7])\b",
    re.I,
)
_ENTRY_RE = re.compile(
    r"\b(new grad(uate)?s?|graduate|fresher|freshers|campus|university|early career|entry[- ]level|"
    r"junior|jr\.?|associate (software|engineer|developer|member|data|analyst)|"
    r"sde[- ]?(i|1)|(engineer|developer|scientist|analyst) (i|1)|mts[- ]?(i|1)|trainee|"
    r"software engineer 1|l[0-3])\b",
    re.I,
)
_MID_RE = re.compile(
    r"\b(sde[- ]?(ii|2)|(engineer|developer|scientist|analyst) (ii|2)|mts[- ]?(ii|2)|l4)\b", re.I
)

LEVELS = ["Intern", "Entry", "Mid", "Senior", "Staff+", "Manager", "Unspecified"]
_PROGRAM_OR_PRODUCT = re.compile(r"product manager|program manager|project manager", re.I)


def classify_role(title: str, departments: str = "") -> tuple[str, bool]:
    for name, tech, pattern in _ROLE_RULES:
        if pattern.search(title):
            return name, tech
    for name, tech, pattern in _ROLE_RULES:
        if departments and pattern.search(departments):
            return name, tech
    return "Other", False


def classify_level(title: str, exp_min: float | None, employment_type: str = "") -> str:
    if (_INTERN_RE.search(title) and not _GET_RE.search(title)) or employment_type == "Internship":
        return "Intern"
    if _MANAGER_RE.search(title) and not _PROGRAM_OR_PRODUCT.search(title):
        return "Manager"
    if _STAFF_RE.search(title):
        return "Staff+"
    if _SENIOR_RE.search(title):
        return "Senior"
    if _MID_RE.search(title):
        return "Mid"
    if _ENTRY_RE.search(title):
        return "Entry"
    if exp_min is None:
        return "Unspecified"
    if exp_min <= 1:
        return "Entry"
    if exp_min <= 4:
        return "Mid"
    if exp_min <= 8:
        return "Senior"
    return "Staff+"


def classify_employment(raw_type: str | None, title: str) -> str:
    t = (raw_type or "").lower().replace("_", " ").replace("-", " ")
    if _INTERN_RE.search(title) and not _GET_RE.search(title):
        return "Internship"
    if "intern" in t:
        return "Internship"
    if any(k in t for k in ("contract", "temporary", "fixed term", "freelance", "consult")):
        return "Contract"
    if "part" in t and "time" in t:
        return "Part-time"
    if any(k in t for k in ("full", "regular", "permanent")):
        return "Full-time"
    if re.search(r"\b(contract|contractor|freelance|temporary)\b", title, re.I):
        return "Contract"
    return "Full-time"
