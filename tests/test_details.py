from jobfinder import details, enrich, score

# Internshala's QuickHyre "Artificial Intelligence (AI)" internship, October 2026: the card
# says the stipend; the detail page only mentions the salary of the job offered afterwards.
DETAIL = {"description_html": (
    "<p>We're looking for a passionate artificial intelligence Intern.</p>"
    "<h3>Additional information</h3><p>Job offer: On successful conversion to a permanent "
    "employee, the candidate can expect a salary of ₹ 1800000 /year</p>")}


def _listing(stipend: str | None) -> dict:
    salary = enrich.parse_salary(f"Stipend: {stipend}" if stipend else "")
    return {"id": "qh", "company": "QuickHyre", "title": "Artificial Intelligence (AI)",
            "location": "Work from home", "scope": "india", "employment_type": "internship",
            "description": "", "source": "internshala",
            "salary_min_lpa": salary["min_lpa"], "salary_max_lpa": salary["max_lpa"],
            "salary_text": salary["text"]}


def test_the_stated_stipend_beats_a_post_internship_salary_in_the_text(profile_file):
    job = details._apply(_listing("₹ 10,000 - 18,000 /month"), DETAIL, score.load_profile())
    assert (job["salary_min_lpa"], job["salary_max_lpa"]) == (1.2, 2.16)
    assert job["salary_text"] == "₹ 10,000 - 18,000 / month"
    assert job["pay_verdict"] == "low"                    # was "target" with 18 LPA


def test_detail_text_still_fills_in_pay_the_listing_did_not_state(profile_file):
    job = details._apply(_listing(None), DETAIL, score.load_profile())
    assert job["salary_max_lpa"] == 18.0


def test_the_detail_pages_own_stipend_replaces_a_wrong_stored_figure(profile_file):
    # A row kept active between listing runs still carried the after-internship salary.
    stale = {**_listing(None), "salary_min_lpa": 2.0, "salary_max_lpa": 2.1,
             "salary_text": "₹ 200000 to 210000"}
    job = details._apply(stale, {**DETAIL, "stipend_text": "₹ 10,000 - 12,000 /month"},
                         score.load_profile())
    assert (job["salary_min_lpa"], job["salary_max_lpa"]) == (1.2, 1.44)


def test_an_unpaid_stipend_never_falls_back_to_the_offer_salary(profile_file):
    job = details._apply(_listing(None), {**DETAIL, "stipend_text": "Unpaid"}, score.load_profile())
    assert job["salary_max_lpa"] is None
    assert job["salary_text"] == "Unpaid"
    assert job["pay_verdict"] == "unpaid"


def test_the_stipend_is_read_from_the_detail_page():
    from jobfinder import feeds
    html = ('<div class="internship_details"><div class="text-container">About the work</div></div>'
            '<div class="other_detail_item stipend_container"><span class="stipend">'
            '₹ 10,000 - 12,000 /month</span></div>')
    assert feeds.parse_internshala_detail(html)["stipend_text"] == "₹ 10,000 - 12,000 /month"
    assert feeds.parse_internshala_detail("<p>no header</p>")["stipend_text"] is None


def test_a_structured_salary_from_the_detail_page_still_wins(profile_file):
    structured = {**DETAIL, "salary_struct": {"min": 300000, "max": 360000, "currency": "INR",
                                              "interval": "year"}}
    job = details._apply(_listing("₹ 10,000 - 18,000 /month"), structured, score.load_profile())
    assert (job["salary_min_lpa"], job["salary_max_lpa"]) == (3.0, 3.6)
