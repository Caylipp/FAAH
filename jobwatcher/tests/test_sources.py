"""Parser gegen gespeicherte echte Seiten (gekürzt). Bricht ein Portal sein Format, fällt das hier zuerst auf."""
import json
from pathlib import Path

from jobwatcher.sources import ba, kleinanzeigen, linkedin, stepstone

F = Path(__file__).parent / "fixtures"


def test_ba_parse():
    items = json.loads((F / "ba.json").read_text())["ergebnisliste"]
    job = ba.parse_item(items[0])
    assert job.source == "ba" and job.title and job.source_id
    assert job.url.startswith("https://www.arbeitsagentur.de/jobsuche/jobdetail/")
    assert job.minijob_flag is not None
    assert job.distance_km is not None


def test_stepstone_parse():
    jobs = stepstone.parse((F / "stepstone.html").read_text())
    assert len(jobs) == 3
    assert all(j.title and j.url.startswith("https://www.stepstone.de/") for j in jobs)
    assert "?" not in jobs[0].url


def test_stepstone_format_change_raises():
    import pytest
    with pytest.raises(ValueError):
        stepstone.parse("<html>nichts</html>")


def test_linkedin_parse():
    jobs = linkedin.parse((F / "linkedin.html").read_text())
    assert len(jobs) == 3
    assert all(j.source_id.isdigit() and j.title and j.company for j in jobs)
    assert "Hesse, Germany" not in jobs[0].location


def test_kleinanzeigen_parse_skips_gesuche():
    from bs4 import BeautifulSoup
    html = (F / "kleinanzeigen.html").read_text()
    arts = BeautifulSoup(html, "lxml").select("article[data-adid]")
    gesuche = {a["data-adid"] for a in arts if "Gesuch" in list(a.stripped_strings)}
    jobs = kleinanzeigen.parse(html)
    assert gesuche and not gesuche & {j.source_id for j in jobs}
    assert len(jobs) == sum(a["data-adid"] not in gesuche for a in arts)
    assert all(j.title and j.url.startswith("https://www.kleinanzeigen.de/s-anzeige/") for j in jobs)
    assert all(j.distance_km is not None for j in jobs)


def test_xing_parse():
    from jobwatcher.sources import xing
    jobs = xing.parse((F / "xing.html").read_text())
    assert len(jobs) == 3
    assert all(j.title and j.url.startswith("https://www.xing.com/jobs/") and j.source_id.isdigit() for j in jobs)
