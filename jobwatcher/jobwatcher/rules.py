"""Regel-Bewertung (0–10) ohne KI: Kategorie, Minijob, Arbeitszeit, Entfernung, Lohn, Ausschlüsse.

Die Regeln laufen für jede Anzeige. Die KI (ai.py) bewertet danach nur die vielversprechenden genauer.
"""
import math
import re

from .models import Job

UEBERFUEHRUNG = r"überführ|ueberfuehr|transferfahrer|fahrzeugtransfer|autotransfer|überführungsfahrer|" \
                r"hol[- /]*(und|&|/)?[- ]*bring|bring[- ]?service|jockey|fahrzeuglogistik|werkstattfahrer|" \
                r"autovermietung|mietwagen.?(fahrer|überführ)|fahrzeugdisposition|umsetzfahrer|" \
                r"fahrzeugbereitstell|testfahrer|zulassungsfahrer|kfz.?kurier|autohaus.{0,30}fahrer|" \
                r"fahrer.{0,30}autohaus"
FAHRER = r"fahrer|kurier|auslieferung|zusteller|fahrdienst|lieferdienst|shuttle|chauffeur|botenfahrt|" \
         r"essen auf rädern|beifahrer|fahrservice"
MINIJOB = r"minijob|mini-job|geringfügig|\b(603|556|538|520|450)(,00)? ?(€|euro|eur)|(603|556|538|520)[- ]?(€|euro)?-?basis|" \
          r"aushilfe|nebenjob|nebentätigkeit|auf abruf|abrufkraft"

# Harte Ausschlüsse: passt sicher nicht
EXCLUDE = [
    (r"\b(lkw|lastkraftwagen|sattelzug|berufskraftfahrer|kraftfahrer|busfahrer|reisebus|linienbus|"
     r"tankwagen|kipper|silofahrer|baggerfahrer|kranfahrer|staplerfahrer|gabelstapler)\b", "Lkw/Bus/Stapler"),
    (r"\bklasse\s*(c1?e?|ce|d1?e?)\b|\b(c1|c1e|ce)\b[- ]?(führerschein|schein)?|fahrerkarte|"
     r"führerschein(klasse)?\s*(c|ce|c1|d)\b", "Führerschein C/CE/D nötig"),
    (r"selbstständig|selbständig|subunternehmer|gewerbeschein|eigenes gewerbe|freiberuf|"
     r"auf rechnung|freelancer|rechnungsstellung", "selbstständig, kein Minijob"),
    (r"\bausbildung (zum|zur)|azubi|auszubildende|duales studium|praktikum|praktikant", "Ausbildung/Praktikum"),
    (r"geldtransport|werttransport|sicherheitsmitarbeiter|§ ?34a", "Sicherheitsdienst (34a)"),
    (r"(uber|bolt|freenow)\b.{0,40}(fahrer|partner)", "Ride-Hailing (meist selbstständig/P-Schein)"),
]
PENALTIES = [
    (r"personenbeförderungsschein|p-schein|fahrerlaubnis zur fahrgastbeförderung|\bfzf\b", -2.0, "P-Schein nötig"),
    (r"werkstudent|studentenjob|immatrikul|eingeschrieben", -2.5, "nur für Studierende"),
    (r"\bvollzeit\b", -1.0, "erwähnt Vollzeit"),
    (r"montag bis freitag|mo\.? ?[-–] ?fr\.?\b|werktags|wochentags", -1.0, "Mo–Fr"),
    (r"vormittags|frühdienst|frühschicht|ab \d ?uhr morgens|zwischen [5-9]( |:00 )?(und|-|–) ?1[0-6]", -1.0,
     "tagsüber unter der Woche"),
    (r"zeitung(en)? austragen|zeitungszusteller|prospektverteil|flyer|werbemittelverteil", -2.0, "Zeitung/Prospekte"),
    (r"zeitarbeit|personaldienstleist|arbeitnehmerüberlassung", -0.5, "Zeitarbeit"),
    (r"winterdienst|schneeräum|streudienst", -2.5, "Winterdienst (Rufbereitschaft, früh morgens)"),
    (r"sozialversicherungspflichtig", -2.0, "sozialversicherungspflichtig (kein Minijob?)"),
]
TIME_BONUS_CAP = 2.0
# Ohne KI können Regeln die Qualität fremder Jobs schlecht beurteilen: Obergrenze je Kategorie
CATEGORY_CAP = {"ueberfuehrung": 10.0, "fahrer": 8.0, "sonstiges": 6.5}
BONUSES = [
    (r"wochenende|samstag|sonntag|sa\.? ?(und|&|/) ?so\.?|weekend", 1.5, "Wochenende"),
    (r"flexibel|freie zeiteinteilung|nach absprache|selbst einteilen|nach verfügbarkeit|auf abruf", 1.0, "flexibel"),
    (r"abends|ab 1[78]( |:)|nach feierabend", 0.5, "abends"),
    (r"eigene[ns]? (pkw|auto|fahrzeug).{0,30}(nicht|kein)|firmenwagen|dienstwagen|fahrzeug wird gestellt", 0.3,
     "Fahrzeug gestellt"),
    (r"bahnticket|deutschlandticket|fahrtkosten.{0,20}(erstattet|übernommen)|rückfahrt.{0,30}(bahn|zug)", 0.5,
     "Rückfahrt bezahlt"),
]

BASE_SCORE = {"ueberfuehrung": 6.0, "fahrer": 3.5, "sonstiges": 1.5}


def classify(text: str) -> str:
    t = text.lower()
    if re.search(UEBERFUEHRUNG, t):
        return "ueberfuehrung"
    if re.search(FAHRER, t):
        return "fahrer"
    return "sonstiges"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def parse_wage(text: str) -> float | None:
    """Höchsten genannten Stundenlohn finden, z. B. "14,50 €/Std." oder "15 Euro pro Stunde"."""
    best = None
    for m in re.finditer(r"(\d{2}(?:[.,]\d{1,2})?)\s*(?:€|euro|eur)\s*(?:/|pro|je|die)?\s*(?:std|stunde|h\b)",
                         text.lower()):
        val = float(m.group(1).replace(",", "."))
        if 12 <= val <= 40:
            best = max(best or 0, val)
    return best


def score(job: Job, cfg: dict) -> Job:
    """Füllt category, rule_score, rule_notes, excluded."""
    text = job.text
    low = text.lower()
    title_low = job.title.lower()
    notes: list[str] = []
    job.category = classify(job.title)
    in_text_only = job.category == "sonstiges" and classify(text) != "sonstiges"

    job.excluded = ""
    for pattern, reason in EXCLUDE:
        # Lkw/Führerschein: nur ausschließen, wenn es im Titel steht oder klar gefordert ist
        target = title_low if reason in ("Lkw/Bus/Stapler", "Ride-Hailing (meist selbstständig/P-Schein)") \
            else low
        if re.search(pattern, target):
            job.excluded = reason
            break
    if job.distance_km is not None and job.distance_km > cfg["home"]["radius_km"] + 5:
        job.excluded = job.excluded or f"zu weit ({job.distance_km:.0f} km)"

    if not job.excluded:
        job.excluded = _requirement_misfit(low, cfg["profile"])

    s = BASE_SCORE[job.category]
    notes.append({"ueberfuehrung": "Überführung/Autohaus", "fahrer": "Fahrerjob", "sonstiges": "anderer Job"}
                 [job.category])
    if in_text_only:
        s += 1.5
        notes.append("Fahren laut Text (+1.5)")

    # Minijob?
    if job.minijob_flag is True or re.search(MINIJOB, title_low):
        s += 1.5
        notes.append("Minijob")
    elif re.search(MINIJOB, low):
        s += 0.8
        notes.append("Minijob erwähnt")
    elif re.search(r"\b(teilzeit|vollzeit|festanstellung|unbefristet)\b", low):
        s -= 2.5
        notes.append("kein Minijob erkennbar")
    else:
        s -= 1.0
        notes.append("Minijob unklar")

    for pattern, delta, label in PENALTIES:
        if re.search(pattern, low):
            s += delta
            notes.append(f"{label} ({delta:+g})")
    bonus = 0.0
    for pattern, delta, label in BONUSES:
        if re.search(pattern, low):
            bonus += delta
            notes.append(f"{label} (+{delta:g})")
    s += min(bonus, TIME_BONUS_CAP)

    # Entfernung
    d = job.distance_km
    if d is None and job.lat is not None and job.lon is not None:
        d = job.distance_km = round(haversine_km(cfg["home"]["lat"], cfg["home"]["lon"], job.lat, job.lon), 1)
    if d is not None:
        if d <= 15:
            s += 1.0
            notes.append(f"nah ({d:.0f} km)")
        elif d > 30:
            s -= 1.0
            notes.append(f"weit ({d:.0f} km)")

    # Lohn
    wage = job.hourly_wage or parse_wage(text)
    if wage:
        job.hourly_wage = wage
        if wage < cfg["scoring"]["min_wage"] - 0.01:
            s -= 1.0
            notes.append(f"unter Mindestlohn ({wage:g} €)")
        elif wage >= 18:
            s += 1.0
            notes.append(f"gut bezahlt ({wage:g} €/h)")
        elif wage >= 15:
            s += 0.5
            notes.append(f"{wage:g} €/h")

    job.rule_score = round(max(0.0, min(CATEGORY_CAP[job.category], s)), 1)
    job.rule_notes = notes
    return job


def _requirement_misfit(low: str, profile: dict) -> str:
    """Mindestalter oder Führerscheinjahre, die die Person (noch) nicht erfüllt."""
    for m in re.finditer(r"(?:mindestens|mind\.|ab|mindestalter:?|älter als)\s*(\d{2})\s*(?:jahre|jahren|j\.)", low):
        age = int(m.group(1))
        window = low[max(0, m.start() - 40):m.end() + 15]
        if 18 < age < 70 and "führerschein" not in window and age > profile.get("age", 99):
            return f"Mindestalter {age}"
    for m in re.finditer(r"führerschein[^.\n]{0,40}?(?:seit|mindestens|mind\.)\s*(?:mindestens\s*)?(\d{1,2})\s*jahr",
                         low):
        years = int(m.group(1))
        if years > profile.get("license_years", 0):
            return f"Führerschein seit {years} Jahren nötig"
    return ""
