"""Kleinanzeigen: Kategorie Jobs (c102) im Umkreis um den Wohnort. Gesuche (Leute, die Arbeit suchen) fallen raus."""
import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Job
from .http import get

log = logging.getLogger(__name__)
BASE = "https://www.kleinanzeigen.de"
URL = BASE + "/s-jobs/{city}/{query}/k0c102l{loc}r{radius}"


def search(cfg: dict, home: dict) -> list[Job]:
    jobs: dict[str, Job] = {}
    radius = min([r for r in (5, 10, 20, 30, 50, 100) if r >= home["radius_km"]] or [100])
    for query in cfg.get("queries", []):
        url = URL.format(city=home["name"].lower(), query=quote(query.replace(" ", "-")),
                         loc=cfg["location_id"], radius=radius)
        for job in parse(get(url).text):
            jobs.setdefault(job.key, job)
    return list(jobs.values())


def parse(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for art in soup.select("article[data-adid]"):
        texts = [t for t in art.stripped_strings]
        if "Gesuch" in texts:
            continue
        link = art.get("data-href") or ""
        title_el = art.select_one("h2, h3") or art.select_one('a[href*="/s-anzeige/"]:not(:has(img))')
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            # Neues Layout ohne Überschrift: Titel ist der erste Text nach Ort/Entfernung/Datum
            title = next((t for t in texts if not re.match(r"^(\d{5} |\(|Heute|Gestern|\d+$)", t)), "")
        dist = None
        for t in texts:
            m = re.match(r"^\((?:ca\. )?(\d+) km\)$", t)
            if m:
                dist = float(m.group(1))
        place = next((t for t in texts if re.match(r"^\d{5} ", t)), "")
        desc_el = art.select_one(".aditem-main--middle--description")
        snippet = desc_el.get_text(" ", strip=True) if desc_el else " ".join(texts)[:600]
        jobs.append(Job(
            source="kleinanzeigen", source_id=art["data-adid"], title=title,
            url=BASE + link if link.startswith("/") else link, location=place, distance_km=dist,
            snippet=snippet[:1500],
            company="Gewerblich" if "PRO" in texts else "",
        ))
    return jobs


def fetch_details(job: Job) -> None:
    soup = BeautifulSoup(get(job.url).text, "lxml")
    desc = soup.select_one("#viewad-description-text")
    if desc:
        job.description = desc.get_text("\n", strip=True)[:6000]
    seller = soup.select_one("#viewad-contact .userprofile-vip a, #viewad-contact .userprofile-vip")
    if seller and job.company in ("", "Gewerblich"):
        job.company = seller.get_text(strip=True)[:80]
