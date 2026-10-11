"""Jobbörse der Bundesagentur für Arbeit (öffentliche REST-API, gleicher Schlüssel wie die Jobsuche-App).

Liste: pc/v6/jobs (Filter arbeitszeit=mj = nur Minijobs). Details: pc/v4/jobdetails/<base64(refnr)>.
"""
import base64
import logging

from ..models import Job
from .http import get

log = logging.getLogger(__name__)
BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{}"


def search(cfg: dict, home: dict) -> list[Job]:
    jobs: dict[str, Job] = {}
    for query in cfg.get("queries", []):
        params = {"wo": home["name"], "umkreis": home["radius_km"], "arbeitszeit": "mj",
                  "angebotsart": 1, "size": 100, "page": 1}
        if query:
            params["was"] = query
        else:
            params["veroeffentlichtseit"] = 7   # Breite Suche (alle Minijobs): nur die letzte Woche
        for page in (1, 2, 3):
            params["page"] = page
            data = get(f"{BASE}/pc/v6/jobs", params=params, headers=HEADERS).json()
            items = data.get("ergebnisliste") or []
            for it in items:
                job = parse_item(it)
                jobs.setdefault(job.key, job)
            if len(items) < params["size"]:
                break
    return list(jobs.values())


def parse_item(it: dict) -> Job:
    ref = it["referenznummer"]
    loc = (it.get("stellenlokationen") or [{}])[0]
    addr = loc.get("adresse", {})
    wage = it.get("festgehalt")
    salary = ""
    if wage:
        unit = "€/h" if it.get("verguetungsangabe") == "STUNDENLOHN" else "€"
        salary = f"{wage:g} {unit}".replace(".", ",")
    return Job(
        source="ba", source_id=ref, title=it.get("stellenangebotsTitel", ""),
        url=DETAIL_URL.format(ref), company=it.get("firma", ""),
        location=" ".join(filter(None, [addr.get("plz"), addr.get("ort")])),
        distance_km=it.get("entfernung"), lat=loc.get("breite"), lon=loc.get("laenge"),
        posted=it.get("datumErsteVeroeffentlichung", ""), salary=salary,
        hourly_wage=wage if it.get("verguetungsangabe") == "STUNDENLOHN" else None,
        minijob_flag=it.get("istGeringfuegigeBeschaeftigung"),
        snippet=" · ".join(filter(None, [it.get("hauptberuf"), _worktime(it)])),
    )


def _worktime(it: dict) -> str:
    names = {"arbeitszeitSchichtNachtWochenende": "Schicht/Nacht/Wochenende",
             "arbeitszeitTeilzeitAbend": "abends", "arbeitszeitTeilzeitFlexibel": "flexibel",
             "arbeitszeitTeilzeitVormittag": "vormittags", "arbeitszeitTeilzeitNachmittag": "nachmittags"}
    found = [label for k, label in names.items() if it.get(k)]
    return ("Arbeitszeit: " + ", ".join(found)) if found else ""


def fetch_details(job: Job) -> None:
    enc = base64.b64encode(job.source_id.encode()).decode()
    data = get(f"{BASE}/pc/v4/jobdetails/{enc}", headers=HEADERS).json()
    job.description = data.get("stellenangebotsBeschreibung", "")[:6000]
