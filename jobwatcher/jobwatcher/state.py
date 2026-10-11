"""Zustand zwischen den Läufen (state.json im State-Branch bzw. lokal in .state/)."""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)
FORGET_AFTER_DAYS = 45


class State:
    def __init__(self, path: Path):
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except ValueError:
            log.warning("state.json beschädigt – starte mit leerem Zustand")
            data = {}
        self.seen: dict[str, dict] = data.get("seen", {})
        self.errors: dict[str, dict] = data.get("errors", {})
        self.meta: dict = data.get("meta", {})
        self.settings: dict = data.get("settings", {})
        self.geocache: dict = data.get("geocache", {})
        self.queue: dict[str, list] = data.get("queue", {"digest": [], "morning": []})

    @property
    def initialized(self) -> bool:
        return bool(self.meta.get("initialized"))

    def fingerprints(self) -> set[str]:
        return {v.get("fp") for v in self.seen.values() if v.get("fp")}

    def mark(self, job, now: datetime, notified: bool = False) -> None:
        stamp = now.isoformat(timespec="seconds")
        entry = self.seen.setdefault(job.key, {"first": stamp, "fp": job.fingerprint, "title": job.title[:80]})
        entry["last"] = stamp
        entry["score"] = job.score
        if notified:
            entry["notified"] = stamp

    def touch(self, keys: list[str], now: datetime) -> None:
        stamp = now.isoformat(timespec="seconds")
        for k in keys:
            if k in self.seen:
                self.seen[k]["last"] = stamp

    def prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=FORGET_AFTER_DAYS)
        for key, info in list(self.seen.items()):
            if datetime.fromisoformat(info["last"]) < cutoff:
                del self.seen[key]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"meta": self.meta, "settings": self.settings, "errors": self.errors,
                                   "queue": self.queue, "geocache": self.geocache, "seen": self.seen},
                                  indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
