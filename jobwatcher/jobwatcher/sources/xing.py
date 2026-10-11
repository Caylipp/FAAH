"""Xing: Trefferliste steckt als Apollo-Cache ("VisibleJob:<id>": {...}) im Seitenquelltext. Kein Login nötig."""
import json
import logging
import re

from bs4 import BeautifulSoup

from ..models import Job
from .http import get

log = logging.getLogger(__name__)
URL = "https://www.xing.com/jobs/search"
KEY_RE = re.compile(r'"VisibleJob:([\w.]+)":\{')


def search(cfg: dict, home: dict) -> list[Job]:
    jobs: dict[str, Job] = {}
    for query in cfg.get("queries", []):
        html = get(URL, params={"keywords": query, "location": home["name"],
                                "radius": min(home["radius_km"], 50)}).text
        for job in parse(html):
            jobs.setdefault(job.key, job)
    return list(jobs.values())


def parse(html: str) -> list[Job]:
    dec = json.JSONDecoder()
    jobs, seen = [], set()
    found_any = False
    for m in KEY_RE.finditer(html):
        found_any = True
        try:
            it, _ = dec.raw_decode(html, m.end() - 1)
        except ValueError:
            continue
        jid = m.group(1).split(".")[0]
        if jid in seen or not it.get("title"):
            continue
        seen.add(jid)
        company = (it.get("companyInfo") or {}).get("companyNameOverride") or ""
        cities = [loc.get("city") for loc in it.get("locations") or [] if loc.get("city")]
        etype = (it.get("employmentType") or {}).get("localizationValue", "")
        jobs.append(Job(
            source="xing", source_id=jid, title=it["title"], url=it.get("url", ""), company=company,
            location=", ".join(cities[:5]), posted=(it.get("refreshedAt") or "")[:10],
            snippet=f"Anstellungsart: {etype}" if etype else "",
        ))
    if not found_any and "jobs" in html and "VisibleJob" not in html:
        raise ValueError("Xing: keine Jobdaten im Seitenquelltext (Format geändert?)")
    return jobs


def fetch_details(job: Job) -> None:
    soup = BeautifulSoup(get(job.url).text, "lxml")
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("description"):
            job.description = BeautifulSoup(data["description"], "lxml").get_text("\n", strip=True)[:6000]
            return
