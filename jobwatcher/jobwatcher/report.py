"""Trefferliste: jobs.json (Daten für /bewerben) und TREFFER.md (auf GitHub am Handy lesbar)."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from .models import Job

KEEP_DAYS = 21
CATEGORY_LABEL = {"ueberfuehrung": "🚗 Überführung", "fahrer": "🚐 Fahrer", "sonstiges": "💼 Minijob"}
SOURCE_LABEL = {"ba": "Arbeitsagentur", "stepstone": "StepStone", "linkedin": "LinkedIn",
                "kleinanzeigen": "Kleinanzeigen", "xing": "Xing"}


def load_jobs(path: Path) -> dict[str, dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def update_jobs(store: dict[str, dict], jobs: list[Job], still_listed: set[str], min_score: float,
                now: datetime) -> None:
    stamp = now.isoformat(timespec="seconds")
    for j in jobs:
        if j.score >= min_score:
            d = j.to_dict()
            d["key"] = j.key
            d["first_seen"] = store.get(j.key, {}).get("first_seen", stamp)
            d["last_seen"] = stamp
            store[j.key] = d
    for key in still_listed & store.keys():
        store[key]["last_seen"] = stamp
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
    for key in [k for k, v in store.items() if v["last_seen"] < cutoff]:
        del store[key]


def active(store: dict[str, dict], now: datetime, hours: int = 36) -> list[dict]:
    """Anzeigen, die zuletzt noch online waren, beste zuerst."""
    cutoff = (now - timedelta(hours=hours)).isoformat()
    items = [v for v in store.values() if v["last_seen"] >= cutoff]
    return sorted(items, key=lambda v: (-score_of(v), v["first_seen"]))


def score_of(d: dict) -> float:
    return d["ai_score"] if d.get("ai_score") is not None else d.get("rule_score", 0)


def line(d: dict) -> str:
    km = f" ({d['distance_km']:.0f} km)" if d.get("distance_km") is not None else ""
    return f"{score_of(d):.1f} · {d['title'][:70]} – {d.get('company') or '?'}{km}"


def write_markdown(path: Path, store: dict[str, dict], cfg: dict, state, now: datetime) -> None:
    push_min = state.settings.get("push_min", cfg["scoring"]["push_min"])
    items = active(store, now)
    top = [d for d in items if score_of(d) >= push_min]
    good = [d for d in items if score_of(d) < push_min]
    out = [f"# Job-Treffer rund um {cfg['home']['name']}",
           "",
           f"Stand: {now:%d.%m.%Y %H:%M} Uhr · {len(top)} Top · {len(good)} weitere · "
           f"Push ab {push_min:g}/10",
           ""]
    errors = [f"{SOURCE_LABEL.get(k, k)} ({v['count']}× Fehler)" for k, v in state.errors.items() if v.get("count")]
    if errors:
        out += [f"> ⚠️ Gerade gestört: {', '.join(errors)}", ""]
    out += ["Bewerbung vorbereiten: auf dem Mac im Ordner `FAAH/jobwatcher` `claude` starten und "
            "`/bewerben <ID>` eingeben.", ""]
    for heading, group in (("🔥 Top-Treffer", top), ("👍 Auch interessant", good)):
        out += [f"## {heading}", ""]
        if not group:
            out += ["_Gerade nichts._", ""]
        for d in group:
            out += _entry(d)
    path.write_text("\n".join(out), encoding="utf-8")


def _entry(d: dict) -> list[str]:
    facts = [CATEGORY_LABEL.get(d.get("category"), "")]
    loc = d.get("location") or "?"
    if d.get("distance_km") is not None:
        loc += f" ({d['distance_km']:.0f} km)"
    facts.append(f"📍 {loc}")
    if d.get("salary") or d.get("hourly_wage"):
        facts.append(f"💶 {d.get('salary') or str(d['hourly_wage']).replace('.', ',') + ' €/h'}")
    facts.append(f"🔎 gefunden {d['first_seen'][8:10]}.{d['first_seen'][5:7]}.")
    facts.append(SOURCE_LABEL.get(d["source"], d["source"]))
    reason = d.get("ai_reason") or ", ".join(d.get("rule_notes", []))
    return [f"### {score_of(d):.1f} · {d['title']}",
            f"**{d.get('company') or 'Firma unbekannt'}** · " + " · ".join(f for f in facts if f),
            "",
            f"> {reason}",
            "",
            f"[Anzeige öffnen]({d['url']}) · ID: `{d['key']}`",
            ""]
