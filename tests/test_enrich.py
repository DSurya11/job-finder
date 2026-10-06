import pytest

from jobfinder import enrich


@pytest.mark.parametrize("location, scope", [
    ("Bangalore, Karnataka, India", "india"),
    ("IN, KA, Bengaluru", "india"),
    ("Hyderabad; San Francisco", "india"),
    ("Remote", "remote_global"),
    ("Remote, APAC", "remote_global"),
    ("Remote - US", "abroad"),
    ("Indianapolis, IN", "abroad"),
    ("London, UK", "abroad"),
    ("2 Locations", "unknown"),
])
def test_locate_scope(location, scope):
    assert enrich.locate(location)["scope"] == scope


def test_locate_canonical_city():
    assert enrich.locate("Gurugram / Remote") == {
        "in_india": True, "cities": ["Delhi NCR"], "remote": True, "scope": "india",
    }


@pytest.mark.parametrize("text, lo, hi", [
    ("CTC: 12-18 LPA for this role", 12, 18),
    ("compensation of 25 LPA", 25, 25),
    ("Stipend: ₹50,000 per month", 6, 6),
    ("Salary INR 15,00,000 - 20,00,000 per annum", 15, 20),
    ("Rs. 40k/month stipend", 4.8, 4.8),
    ("We serve 5 lakh users daily", None, None),
    ("The pay range is $120,000 - $150,000 annually", None, None),
])
def test_parse_salary(text, lo, hi):
    out = enrich.parse_salary(text)
    assert (out["min_lpa"], out["max_lpa"]) == (lo, hi)


def test_usd_salary_is_text_only():
    assert "USD" in enrich.parse_salary("The pay range is $120,000 - $150,000 annually")["text"]


@pytest.mark.parametrize("text, expected", [
    ("5+ years of experience in Java. 2+ years in AWS", (5, None)),
    ("2-4 years experience", (2, 4)),
    ("Freshers welcome", (0, 1)),
    ("Founded 10 years ago, we are great", (None, None)),
])
def test_parse_experience(text, expected):
    assert enrich.parse_experience(text) == expected


@pytest.mark.parametrize("title, role, level", [
    ("Software Engineer Intern", "Software Engineering", "Intern"),
    ("SDE II, Payments", "Software Engineering", "Mid"),
    ("Senior Backend Engineer", "Backend", "Senior"),
    ("Staff ML Engineer", "ML / AI", "Staff+"),
    ("Graduate Engineer Trainee", "Software Engineering", "Entry"),
    ("Engineering Manager", "Software Engineering", "Manager"),
    ("SoC Design Engineer", "Embedded / Hardware", "Unspecified"),
    ("Account Executive", "Sales / Marketing", "Unspecified"),
])
def test_classify(title, role, level):
    assert enrich.classify_role(title)[0] == role
    assert enrich.classify_level(title, None) == level


def test_html_to_text_unescapes_greenhouse_content():
    raw = "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
    assert enrich.html_to_text(raw) == "Hello & welcome\n\n• Python"


from jobfinder import pay

_PROFILE = {"raw": {"job_preferences": {"min_lpa": 9, "target_lpa": 12}}}


def _job(**kw):
    base = {"title": "Software Engineer", "employment_type": "Full-time", "level": "Entry",
            "source": "greenhouse", "description": "", "salary_text": ""}
    return {**base, **kw}


@pytest.mark.parametrize("job, verdict", [
    (_job(salary_max_lpa=14), "target"),
    (_job(salary_max_lpa=10), "ok"),
    (_job(salary_max_lpa=5), "low"),
    (_job(), "unknown"),
    (_job(est_min_lpa=10, est_max_lpa=15), "estimated"),
    (_job(est_min_lpa=6, est_max_lpa=14), "estimated"),
    (_job(est_min_lpa=5.8, est_max_lpa=11), "low"),
    (_job(est_max_lpa=6), "low"),
    (_job(level="Intern", employment_type="Internship", salary_max_lpa=12, salary_text="₹1,00,000 / month"), "target"),
    (_job(level="Intern", employment_type="Internship", salary_max_lpa=9.6, salary_text="₹80,000 / month"), "ok"),
    (_job(level="Intern", employment_type="Internship", salary_max_lpa=6, salary_text="₹50,000 / month"), "low"),
    (_job(level="Intern", employment_type="Internship", salary_max_lpa=1.2, salary_text="₹10,000 / month"), "low"),
    (_job(level="Intern", employment_type="Internship", salary_max_lpa=5, salary_text="₹ 400000 to 500000"), "low"),
    (_job(source="internshala", description="Stipend: Unpaid"), "unpaid"),
    (_job(source="internshala", description="Candidates must pay a registration fee of Rs 2000"), "suspicious"),
    (_job(source="linkedin", description="We will never charge a registration fee."), "unknown"),
    (_job(description="Reconcile security deposit accounts"), "unknown"),
])
def test_pay_verdict(job, verdict):
    assert pay.judge(job, _PROFILE) == verdict
