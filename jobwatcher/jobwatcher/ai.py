"""KI-Bewertung mit Google Gemini (Gratis-Key). Mehrere Anzeigen pro Anfrage, um das Kontingent zu schonen.

Fällt die KI aus (kein Key, Kontingent leer, Fehler), bleibt die Regel-Bewertung stehen.
"""
import json
import logging
import time

import requests

from .models import Job

log = logging.getLogger(__name__)
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BATCH = 8

PROMPT = """Du bewertest Stellenanzeigen für eine Person, die einen Minijob sucht.

PROFIL:
{profile}

VERFÜGBARKEIT:
{availability}

BEWERTE jede Anzeige mit einer Zahl von 0 bis 10, wie gut sie passt:
- 9–10: Fahrzeugüberführung/Hol- und Bringservice/Autohaus-Fahrer als Minijob, Wochenende möglich, nah. Sofort bewerben.
- 7–8: sehr guter Minijob (z. B. Fahrer mit Pkw, gut bezahlt, Wochenende/flexibel), oder Überführung mit kleinen Abstrichen.
- 5–6: passabel, aber deutliche Abstriche (Zeiten unklar, nur Mo–Fr ab 17:30 möglich, weit weg, schlecht bezahlt).
- 0–4: passt nicht. Immer 0–2, wenn: kein Minijob (Vollzeit/Teilzeit/Midijob ohne Minijob-Option), selbstständig/Gewerbe,
  Lkw/Bus/Klasse C/CE/D nötig, Personenbeförderungsschein nötig, nur für Studierende/Werkstudenten, Arbeitszeiten nur
  tagsüber Mo–Fr, oder die Anzeige ist ein Gesuch/Spam.
Wochenend-Einsätze (Sonntag, Samstag vor 14 Uhr) sind ein großes Plus. Gehalt unter Mindestlohn (13,90 €/h) ist ein Minus.

Antworte NUR mit JSON: eine Liste mit einem Objekt pro Anzeige, gleiche Reihenfolge:
[{{"id": "<id>", "score": <0-10>, "reason": "<max. 120 Zeichen, Deutsch, warum>"}}]

ANZEIGEN:
{jobs}
"""

SCHEMA = {
    "type": "ARRAY",
    "items": {"type": "OBJECT",
              "properties": {"id": {"type": "STRING"}, "score": {"type": "NUMBER"}, "reason": {"type": "STRING"}},
              "required": ["id", "score", "reason"]},
}


class Gemini:
    def __init__(self, api_key: str, models: list[str], cfg: dict):
        self.api_key = api_key
        self.models = list(models)
        self.cfg = cfg
        self.disabled_reason = "" if api_key else "kein GEMINI_API_KEY"
        self.calls = 0

    def rate(self, jobs: list[Job]) -> int:
        """Setzt ai_score/ai_reason. Gibt die Anzahl bewerteter Anzeigen zurück."""
        rated = 0
        for i in range(0, len(jobs), BATCH):
            if self.disabled_reason:
                break
            batch = jobs[i:i + BATCH]
            results = self._ask(batch)
            by_id = {str(r.get("id")): r for r in results or []}
            for n, job in enumerate(batch):
                r = by_id.get(str(n))
                if r is None:
                    continue
                try:
                    job.ai_score = round(max(0.0, min(10.0, float(r["score"]))), 1)
                    job.ai_reason = str(r.get("reason", ""))[:200]
                    rated += 1
                except (TypeError, ValueError, KeyError):
                    pass
        return rated

    def _prompt(self, batch: list[Job]) -> str:
        blocks = []
        for n, j in enumerate(batch):
            dist = f"{j.distance_km:.0f} km" if j.distance_km is not None else "unbekannt"
            body = (j.description or j.snippet)[:2500]
            blocks.append(f"--- id: {n}\nTitel: {j.title}\nFirma: {j.company}\nOrt: {j.location} "
                          f"(Entfernung {dist})\nLohn: {j.salary or 'k. A.'}\n"
                          f"Minijob laut Portal: {'ja' if j.minijob_flag else 'unbekannt'}\nText:\n{body}")
        return PROMPT.format(profile=self.cfg["profile"]["text"],
                             availability=self.cfg["availability"]["text"], jobs="\n\n".join(blocks))

    def _ask(self, batch: list[Job]) -> list[dict] | None:
        body = {"contents": [{"parts": [{"text": self._prompt(batch)}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json",
                                     "responseSchema": SCHEMA}}
        while self.models:
            model = self.models[0]
            for attempt in (1, 2):
                try:
                    self.calls += 1
                    resp = requests.post(URL.format(model=model), json=body, timeout=60,
                                         headers={"x-goog-api-key": self.api_key})
                except requests.RequestException as e:
                    log.warning("Gemini nicht erreichbar: %s", e)
                    if attempt == 2:
                        return None
                    time.sleep(5)
                    continue
                if resp.status_code == 429:
                    if attempt == 1:
                        time.sleep(20)
                        continue
                    self.disabled_reason = "Gemini-Kontingent erschöpft (429)"
                    log.warning(self.disabled_reason)
                    return None
                if resp.status_code in (400, 401, 403) and "API key" in resp.text:
                    self.disabled_reason = f"Gemini-Key ungültig ({resp.status_code})"
                    log.warning(self.disabled_reason)
                    return None
                if resp.status_code == 404:
                    log.warning("Gemini-Modell %s nicht verfügbar, nehme das nächste", model)
                    self.models.pop(0)
                    break
                if resp.status_code >= 400:
                    log.warning("Gemini-Fehler %s: %s", resp.status_code, resp.text[:300])
                    if attempt == 2:
                        return None
                    time.sleep(5)
                    continue
                try:
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    data = json.loads(text)
                    return data if isinstance(data, list) else None
                except (KeyError, IndexError, ValueError) as e:
                    log.warning("Gemini-Antwort nicht lesbar: %s", e)
                    return None
        self.disabled_reason = "kein Gemini-Modell verfügbar"
        return None
