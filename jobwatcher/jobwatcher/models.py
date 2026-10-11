"""Datenmodell für eine Stellenanzeige."""
import hashlib
import re
from dataclasses import asdict, dataclass, field


@dataclass
class Job:
    source: str                     # ba | stepstone | linkedin | kleinanzeigen
    source_id: str
    title: str
    url: str
    company: str = ""
    location: str = ""
    distance_km: float | None = None
    lat: float | None = None
    lon: float | None = None
    posted: str = ""                # ISO-Datum, soweit bekannt
    snippet: str = ""               # Kurztext aus der Trefferliste
    description: str = ""           # Volltext, nur für vielversprechende Anzeigen geladen
    salary: str = ""                # z. B. "13,90 €/h"
    hourly_wage: float | None = None
    minijob_flag: bool | None = None  # True = Quelle sagt sicher Minijob (BA), None = unbekannt
    # Bewertung
    category: str = ""              # ueberfuehrung | fahrer | sonstiges
    rule_score: float = 0.0
    rule_notes: list[str] = field(default_factory=list)
    excluded: str = ""              # Grund für harten Ausschluss, leer = nicht ausgeschlossen
    ai_score: float | None = None
    ai_reason: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Gleiche Stelle auf mehreren Portalen erkennen: normalisierter Titel + Firma."""
        norm = lambda s: re.sub(r"\(.*?\)|[^a-z0-9äöüß]", "", s.lower())
        who = self.company if self.company not in ("", "Gewerblich") else f"{self.source}:{self.location}"
        return hashlib.sha1(f"{norm(self.title)}|{norm(who)}".encode()).hexdigest()[:12]

    @property
    def score(self) -> float:
        if self.excluded:
            return 0.0
        return self.ai_score if self.ai_score is not None else self.rule_score

    @property
    def text(self) -> str:
        return " ".join(filter(None, [self.title, self.company, self.snippet, self.description]))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        known = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in known})
