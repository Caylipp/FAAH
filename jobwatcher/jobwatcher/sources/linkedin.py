"""LinkedIn: öffentliche Gast-Schnittstelle (ohne Login), dieselbe, die die Jobsuche ohne Anmeldung nutzt."""
import logging
import re

from bs4 import BeautifulSoup

from ..models import Job
from .http import get

log = logging.getLogger(__name__)
SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"


def search(cfg: dict, home: dict) -> list[Job]:
    jobs: dict[str, Job] = {}
    miles = round(home["radius_km"] / 1.609)
    for query in cfg.get("queries", []):
        html = get(SEARCH, params={"keywords": query, "location": f"{home['name']}, Hessen, Deutschland",
                                   "distance": miles, "f_TPR": "r1209600", "start": 0}).text
        for job in parse(html):
            jobs.setdefault(job.key, job)
    return list(jobs.values())


def parse(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for card in soup.select("div.base-search-card"):
        urn = card.get("data-entity-urn", "")
        m = re.search(r"(\d+)$", urn)
        title = card.select_one(".base-search-card__title")
        if not m or not title:
            continue
        link = card.select_one("a.base-card__full-link")
        company = card.select_one(".base-search-card__subtitle")
        loc = card.select_one(".job-search-card__location")
        posted = card.select_one("time")
        salary = card.select_one(".job-search-card__salary-info")
        jobs.append(Job(
            source="linkedin", source_id=m.group(1), title=title.get_text(strip=True),
            url=(link["href"].split("?")[0] if link else f"https://www.linkedin.com/jobs/view/{m.group(1)}"),
            company=company.get_text(strip=True) if company else "",
            location=loc.get_text(strip=True).replace(", Hesse, Germany", "") if loc else "",
            posted=posted.get("datetime", "") if posted else "",
            salary=salary.get_text(" ", strip=True) if salary else "",
        ))
    return jobs


def fetch_details(job: Job) -> None:
    html = get(DETAIL.format(job.source_id)).text
    soup = BeautifulSoup(html, "lxml")
    desc = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
    if desc:
        job.description = desc.get_text("\n", strip=True)[:6000]
    crit = [li.get_text(" ", strip=True) for li in soup.select(".description__job-criteria-item")]
    if crit:
        job.snippet = " · ".join(crit)
