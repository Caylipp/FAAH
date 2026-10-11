"""Steuerung vom Handy: Befehle an das geheime Steuer-Topic (NTFY_CONTROL_TOPIC) schicken.

GitHub Actions läuft nicht dauerhaft. Darum holt jeder Lauf die seit dem letzten Lauf eingegangenen Befehle ab
(ntfy hält Nachrichten 12 Stunden vor). Ein Befehl wirkt also spätestens beim nächsten Lauf (≤ 30 Minuten).

Befehle (Groß-/Kleinschreibung egal):
  status · top · pause <Stunden> · weiter · schwelle <Zahl> · quelle <name> an|aus · hilfe
"""
import json
import logging
from datetime import datetime, timedelta

import requests

from . import config

log = logging.getLogger(__name__)
SOURCE_NAMES = {"ba": "ba", "arbeitsagentur": "ba", "stepstone": "stepstone", "linkedin": "linkedin",
                "kleinanzeigen": "kleinanzeigen", "ka": "kleinanzeigen", "xing": "xing"}
HELP = ("Befehle (wirken beim nächsten Lauf, spätestens nach 30 Min.):\n"
        "status · top\npause <Stunden> · weiter\nschwelle <Zahl> (z. B. schwelle 6.5)\n"
        "quelle <ba|stepstone|linkedin|kleinanzeigen|xing> an|aus\nhilfe")


def fetch_commands(state) -> list[str]:
    if not config.CONTROL_TOPIC:
        return []
    since = state.meta.get("control_since") or "12h"
    try:
        resp = requests.get(f"{config.NTFY_SERVER}/{config.CONTROL_TOPIC}/json",
                            params={"poll": 1, "since": since}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("Steuer-Topic nicht abrufbar: %s", e)
        return []
    cmds = []
    for line in resp.text.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("event") != "message":
            continue
        state.meta["control_since"] = msg["id"]
        if msg.get("message"):
            cmds.append(msg["message"].strip())
    return cmds


def apply(cmd: str, state, cfg: dict, now: datetime) -> tuple[str, str] | None:
    """Führt einen Befehl aus. Gibt (Titel, Text) für die Antwort-Push zurück. "top"/"status" baut der Runner."""
    words = cmd.lower().replace(",", ".").split()
    if not words:
        return None
    s = state.settings
    head, rest = words[0], words[1:]
    if head in ("pause", "stop") :
        hours = float(rest[0]) if rest and _num(rest[0]) else 8
        until = now + timedelta(hours=hours)
        s["paused_until"] = until.isoformat(timespec="minutes")
        return "⏸ Pause", f"Keine Pushes bis {until:%a %H:%M} Uhr. Gesucht wird weiter.\n„weiter“ hebt die Pause auf."
    if head in ("weiter", "resume", "start"):
        s.pop("paused_until", None)
        return "▶️ Weiter", "Pushes sind wieder an."
    if head in ("schwelle", "threshold") and rest and _num(rest[0]):
        val = max(3.0, min(10.0, float(rest[0])))
        s["push_min"] = val
        return "🎚 Schwelle", f"Pushes ab Bewertung {val:g}/10 (Top-Alarm ab {max(val, cfg['scoring']['top_min']):g})."
    if head == "quelle" and len(rest) >= 2 and rest[0] in SOURCE_NAMES:
        name = SOURCE_NAMES[rest[0]]
        off = set(s.get("sources_off", []))
        if rest[1] in ("aus", "off"):
            off.add(name)
        else:
            off.discard(name)
        s["sources_off"] = sorted(off)
        return "🔌 Quelle", f"{name}: {'AUS' if name in off else 'AN'}"
    if head in ("status", "top"):
        return head, ""
    return "❓ Befehl unbekannt", f"„{cmd}“\n\n{HELP}"


def _num(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False
