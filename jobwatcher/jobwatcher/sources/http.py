"""Gemeinsame HTTP-Sitzung: Browser-Kennung, Timeout, eine Wiederholung bei Netzfehlern."""
import logging
import time

import requests

from ..config import USER_AGENT

log = logging.getLogger(__name__)
_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"})
    return _session


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: int = 15) -> requests.Response:
    """Bei Timeout kein zweiter Versuch: ein blockierendes Portal würde sonst Actions-Minuten fressen."""
    for attempt in (1, 2):
        try:
            resp = session().get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt == 1:
                time.sleep(3)
                continue
            resp.raise_for_status()
            if "charset" not in resp.headers.get("content-type", "").lower():
                resp.encoding = "utf-8"     # sonst rät requests ISO-8859-1 und Umlaute zerfallen
            return resp
        except requests.Timeout:
            raise
        except requests.ConnectionError:
            if attempt == 2:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def strip_html(html: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(html or "", "lxml").get_text("\n", strip=True)
