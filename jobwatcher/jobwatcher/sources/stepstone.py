"""StepStone: Trefferliste als JSON im Seitenquelltext (window.__PRELOADED_STATE__["app-unifiedResultlist"])."""
import json
import logging
import re

from ..models import Job
from .http import get, strip_html

log = logging.getLogger(__name__)
URL = "https://www.stepstone.de/jobs/{query}/in-{city}"
STATE_RE = re.compile(r'window\.__PRELOADED_STATE__\["app-unifiedResultlist"\]\s*=\s*(.*?);\s*</script>', re.S)


def search(cfg: dict, home: dict) -> list[Job]:
    jobs: dict[str, Job] = {}
    city = home["name"].lower()
    for query in cfg.get("queries", []):
        html = get(URL.format(query=query, city=city),
                   params={"radius": min(home["radius_km"], 50), "sort": 2, "action": "sort_publish"}).text
        for job in parse(html):
            jobs.setdefault(job.key, job)
    return list(jobs.values())


def parse(html: str) -> list[Job]:
    m = STATE_RE.search(html)
    if not m:
        raise ValueError("StepStone: Trefferliste nicht im Seitenquelltext gefunden (Format geändert?)")
    items = json.loads(m.group(1)).get("searchResults", {}).get("items", [])
    jobs = []
    for it in items:
        if it.get("section") not in (None, "main", "regional", "semantic"):
            continue
        snippet = strip_html(it.get("textSnippet", "")) + "\n" + strip_html(it.get("jobBenefitsHtml", ""))
        salary = (it.get("unifiedSalary") or {}).get("formatted", "") if isinstance(it.get("unifiedSalary"), dict) else ""
        jobs.append(Job(
            source="stepstone", source_id=str(it["id"]), title=it.get("title", ""),
            url=it.get("url", "").split("?")[0], company=it.get("companyName", ""),
            location=it.get("location", ""), posted=(it.get("datePosted") or "")[:10],
            snippet=snippet.strip()[:2000], salary=salary or "",
        ))
    return jobs


def fetch_details(job: Job) -> None:
    """Die Liste enthält schon Auszug und Benefits. Volltext nur, wenn der Auszug sehr kurz ist."""
    if len(job.snippet) > 300:
        return
    html = get(job.url).text
    m = re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            job.description = strip_html(data.get("description", ""))[:6000]
        except (ValueError, AttributeError):
            pass
