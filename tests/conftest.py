import pytest

from jobfinder import score

PROFILE = """\
personal:
  name: Test Person
  email: test@example.com
  phone: '99999'
skills:
  primary: [Python]
job_preferences:
  type: full-time
  # Pay floors.
  min_lpa: 9                     # below this a full-time job is marked low pay
  target_lpa: 12                 # what you are aiming for
"""


@pytest.fixture
def profile_file(tmp_path, monkeypatch):
    """A throwaway user_profile.yaml in place of the real one.

    load_profile() is cached per process, so the cache is cleared on the way in (or a
    profile read earlier would be returned instead of this one) and on the way out (or
    this one would leak into later tests).
    """
    path = tmp_path / "user_profile.yaml"
    path.write_text(PROFILE, encoding="utf-8")
    monkeypatch.setattr(score, "PROFILE_PATH", path)
    score.load_profile.cache_clear()
    yield path
    score.load_profile.cache_clear()
