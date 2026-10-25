import re

import pytest

from jobfinder import score

PROFILE = """\
education:
  degree: "B.Tech CSE"
skills:
  primary: [Kubernetes, Docker, Terraform, AWS, Python, Linux]
job_preferences:
  type: full-time
  min_lpa: 12
  target_lpa: 18
  levels: [Entry]
  preferred_locations: [India]
  roles: ["DevOps Engineer", "Backend Engineer (Python)", "Software Engineer"]
"""


@pytest.fixture
def profile(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(PROFILE, encoding="utf-8")
    score.load_profile.cache_clear()
    yield score.load_profile(str(path))
    score.load_profile.cache_clear()


def _job(**kw) -> dict:
    base = {"title": "Engineer", "description": "We build things.", "level": "Entry",
            "role": "Software Engineering", "is_tech": 1, "cities": ["Pune"], "location": "Pune",
            "scope": "india", "source": "greenhouse", "pay_verdict": "ok", "posted_at": "2026-01-01"}
    return {**base, **kw}


def _points(reasons: list[str]) -> float:
    return sum(float(m.group(2)) * (1 if m.group(1) == "+" else -1)
               for r in reasons if (m := re.search(r"([+−])(\d+(?:\.\d+)?)$", r)))


def test_each_reason_carries_its_points_and_they_add_up(profile):
    value, reasons = score.score_job(_job(description="Kubernetes, Docker and Python."), profile)
    assert reasons[0] == "Entry role +35"
    assert value == _points(reasons)


def test_the_first_listed_role_counts_most(profile):
    assert profile["families"] == ["DevOps / SRE", "Backend", "Software Engineering"]
    main = score.score_job(_job(role="DevOps / SRE"), profile)[0]
    other = score.score_job(_job(role="Backend"), profile)[0]
    tech = score.score_job(_job(role="Data Engineering"), profile)[0]
    assert (main - other, other - tech) == (5, 3)              # 15, 10, 7


def test_more_of_your_skills_scores_higher(profile):
    three = score.score_job(_job(description="Kubernetes, Docker, Python"), profile)[0]
    six = score.score_job(_job(description="Kubernetes, Docker, Python, Terraform, AWS, Linux"), profile)[0]
    assert six - three == 17                                   # 35 * 9/18 = 18 -> 35


@pytest.mark.parametrize("description, required", [
    # Real lines from October 2026 postings.
    ("Required Qualifications:\n• PhD from a premier Indian institution (IISc, IITs) with 0-2 years of "
     "relevant experience, or Masters from a premier Indian institution with 5+ years", True),
    ("Master's degree in Computer Science or Statistics is required.", True),
    ("- PhD, or Master's degree and 4+ years of CS, CE, ML or related field experience", True),
    ("Minimum qualifications:\nBachelor's degree or equivalent practical experience.\n"
     "Preferred qualifications:\nMaster's degree or PhD in Computer Science or related technical field.", False),
    ("Qualification: B.E. or M.Tech. in Computer Science", False),
    ("Bachelor's with 8 years of related experience\nOR PhD 4 years of related experience", False),
    ("5 - 8 years of ML engineering experience, or 2+ years with a Ph.D.", False),
    ("PhD is a plus.", False),
])
def test_a_degree_counts_only_when_required(description, required):
    assert bool(score.needs_advanced_degree(description)) is required


def test_a_required_phd_costs_points_even_when_the_title_does_not_say_so(profile):
    phd = "Required Qualifications:\n• PhD from a premier Indian institution with 0-2 years"
    value, reasons = score.score_job(_job(title="Research Scientist", description=phd), profile)
    assert "Requires a PhD or Master's −30" in reasons
