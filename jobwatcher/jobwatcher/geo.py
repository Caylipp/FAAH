"""Entfernung für Anzeigen ohne Koordinaten (StepStone, LinkedIn): Ort per OpenStreetMap-Nominatim nachschlagen.

Ergebnisse werden im Zustand zwischengespeichert, damit jede Stadt nur einmal abgefragt wird (Nominatim erlaubt 1/s).
"""
import logging
import re
import time

import requests

from .rules import haversine_km

log = logging.getLogger(__name__)
URL = "https://nominatim.openstreetmap.org/search"
MAX_LOOKUPS_PER_RUN = 15


class Geocoder:
    def __init__(self, cache: dict, home: dict):
        self.cache = cache          # Ort -> [lat, lon] oder None
        self.home = home
        self.lookups = 0

    def distance(self, location: str) -> float | None:
        """Bei mehreren Orten ("Hamburg, Köln, Frankfurt") zählt der nächste."""
        places = [p.strip() for p in re.split(r"[,/;]| oder | und ", location) if p.strip()]
        best = None
        for place in places[:12]:
            place = re.sub(r"^\d{5}\s+", "", place)
            coords = self._lookup(place)
            if coords:
                d = haversine_km(self.home["lat"], self.home["lon"], *coords)
                best = d if best is None else min(best, d)
        return round(best, 1) if best is not None else None

    def _lookup(self, place: str):
        key = place.lower()
        if key in self.cache:
            return self.cache[key]
        if self.lookups >= MAX_LOOKUPS_PER_RUN:
            return None
        self.lookups += 1
        try:
            time.sleep(1.1)
            resp = requests.get(URL, params={"q": place, "countrycodes": "de", "format": "json", "limit": 1},
                                headers={"User-Agent": "faah-jobwatcher/1.0 (private job alert)"}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            coords = [float(data[0]["lat"]), float(data[0]["lon"])] if data else None
        except (requests.RequestException, ValueError, KeyError) as e:
            log.warning("Geocoding für %r fehlgeschlagen: %s", place, e)
            return None
        self.cache[key] = coords
        return coords
