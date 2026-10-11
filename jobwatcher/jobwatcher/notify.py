"""Push-Benachrichtigungen über ntfy (JSON-Veröffentlichung, damit Umlaute und Emojis sicher ankommen)."""
import logging
import time

import requests

from . import config

log = logging.getLogger(__name__)
SENT: list[dict] = []      # für Tests und Trockenlauf


def send(title: str, message: str, *, priority: int = 3, tags: tuple[str, ...] = (),
         click: str | None = None, actions: list[dict] | None = None, dry: bool = False) -> bool:
    payload = {"topic": config.NTFY_TOPIC, "title": title, "message": message,
               "priority": priority, "tags": list(tags)}
    if click:
        payload["click"] = click
    if actions:
        payload["actions"] = actions[:3]
    SENT.append(payload)
    if dry or not config.NTFY_TOPIC:
        log.info("[kein Push] %s | %s", title, message.replace("\n", " / ")[:200])
        return False
    for delay in (5, 15, None):
        try:
            resp = requests.post(config.NTFY_SERVER, json=payload, timeout=20)
            resp.raise_for_status()
            log.info("Push gesendet: %s", title)
            return True
        except requests.RequestException as e:
            if delay is None:
                log.error("Push fehlgeschlagen: %s", e)
                return False
            time.sleep(delay)
    return False


def view(label: str, url: str) -> dict:
    return {"action": "view", "label": label, "url": url, "clear": False}


def command(label: str, cmd: str) -> dict | None:
    """Knopf, der einen Befehl an das Steuer-Topic schickt (wird beim nächsten Lauf ausgeführt)."""
    if not config.CONTROL_TOPIC:
        return None
    return {"action": "http", "label": label, "url": f"{config.NTFY_SERVER}/{config.CONTROL_TOPIC}",
            "method": "POST", "body": cmd, "clear": True}
