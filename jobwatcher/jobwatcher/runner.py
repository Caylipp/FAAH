"""Ein Lauf: Befehle abholen → Quellen abfragen → bewerten → melden → Zustand und Trefferliste schreiben."""
import logging
from datetime import datetime
from pathlib import Path

from . import config, control, notify, report, rules
from .ai import Gemini
from .geo import Geocoder
from .models import Job
from .sources import SOURCES
from .state import State

log = logging.getLogger(__name__)
MAX_DETAILS_PER_RUN = 45
MAX_PUSHES_PER_RUN = 5
SOURCE_ALERT_AFTER = 6          # aufeinanderfolgende Fehlversuche, bevor eine Quelle gemeldet wird
BACKOFF_AFTER = 2               # ab so vielen Fehlversuchen in Folge wird die Quelle seltener versucht …
BACKOFF_EVERY = 4               # … nur noch jeden 4. Lauf (≈ alle 2 Stunden), spart Actions-Minuten


class Runner:
    def __init__(self, state_dir: Path, cfg: dict | None = None, dry: bool = False, now: datetime | None = None):
        self.cfg = cfg or config.load_config()
        self.state_dir = state_dir
        self.state = State(state_dir / "state.json")
        self.jobs_path = state_dir / "jobs.json"
        self.store = report.load_jobs(self.jobs_path)
        self.dry = dry
        self.now = now or datetime.now(config.TZ)
        self.ai = Gemini(config.GEMINI_API_KEY, self.cfg["ai"]["models"], self.cfg)
        self.geo = Geocoder(self.state.geocache, self.cfg["home"])
        self.stats = {"found": 0, "new": 0, "rated": 0, "pushed": 0}
        self.postponed: set[str] = set()

    # ---------- Einstellungen ----------
    @property
    def push_min(self) -> float:
        return float(self.state.settings.get("push_min", self.cfg["scoring"]["push_min"]))

    @property
    def top_min(self) -> float:
        return max(self.push_min, float(self.cfg["scoring"]["top_min"]))

    def paused(self) -> bool:
        until = self.state.settings.get("paused_until")
        if until and datetime.fromisoformat(until) > self.now:
            return True
        self.state.settings.pop("paused_until", None)
        return False

    def quiet(self) -> bool:
        q = self.cfg["quiet_hours"]
        h = self.now.hour
        return h >= q["start"] or h < q["end"] if q["start"] > q["end"] else q["start"] <= h < q["end"]

    # ---------- Ablauf ----------
    def run(self) -> dict:
        self.handle_commands()
        current = self.collect()
        listed = {j.key for j in current}
        self.state.touch(list(listed), self.now)

        fps = self.state.fingerprints()
        fresh = []
        for j in current:
            if j.key in self.state.seen:
                continue
            if j.fingerprint in fps:      # gleiche Stelle schon von einem anderen Portal bekannt
                rules.score(j, self.cfg)
                self.state.mark(j, self.now)
                continue
            fps.add(j.fingerprint)
            fresh.append(j)
        self.stats["new"] = len(fresh)

        processed = self.evaluate(fresh)
        report.update_jobs(self.store, processed, listed, self.cfg["scoring"]["digest_min"], self.now)

        if not self.state.initialized:
            # Erststart: Bestand nur merken, nicht einzeln melden. Erst wenn alles bewertet ist, eine Übersicht.
            for j in processed:
                self.state.mark(j, self.now)
            if not self.postponed:
                self.state.meta["initialized"] = self.now.isoformat(timespec="seconds")
                self.first_run_summary()
        else:
            self.notify_jobs(processed)
        self.flush_morning_queue()
        self.maybe_digest()
        self.maybe_heartbeat()

        self.state.prune(self.now)
        self.state.meta.update(last_run=self.now.isoformat(timespec="seconds"),
                               runs=self.state.meta.get("runs", 0) + 1,
                               last_stats=self.stats)
        self.save()
        log.info("Fertig: %s", self.stats)
        return self.stats

    def save(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state.save()
        import json
        self.jobs_path.write_text(json.dumps(self.store, indent=1, ensure_ascii=False), encoding="utf-8")
        report.write_markdown(self.state_dir / "TREFFER.md", self.store, self.cfg, self.state, self.now)

    # ---------- Quellen ----------
    def collect(self) -> list[Job]:
        off = set(self.state.settings.get("sources_off", []))
        jobs: list[Job] = []
        for name, mod in SOURCES.items():
            scfg = self.cfg["sources"].get(name, {})
            if not scfg.get("enabled", True) or name in off:
                continue
            err = self.state.errors.get(name, {})
            if err.get("count", 0) >= BACKOFF_AFTER:
                err["skipped"] = err.get("skipped", 0) + 1
                if err["skipped"] % BACKOFF_EVERY:
                    log.info("Quelle %s ausgelassen (gestört, nächster Versuch später)", name)
                    continue
            try:
                found = mod.search(scfg, self.cfg["home"])
            except Exception as e:   # eine kaputte Quelle darf den Lauf nicht stoppen
                log.warning("Quelle %s fehlgeschlagen: %s", name, e)
                self.source_failed(name, e)
                continue
            if not found:
                log.warning("Quelle %s: 0 Treffer", name)
            self.source_ok(name)
            log.info("Quelle %s: %d Anzeigen", name, len(found))
            jobs += found
        self.stats["found"] = len(jobs)
        return jobs

    def source_failed(self, name: str, err: Exception) -> None:
        e = self.state.errors.setdefault(name, {"count": 0})
        e["count"] += 1
        e["last"] = f"{type(err).__name__}: {str(err)[:150]}"
        if e["count"] == SOURCE_ALERT_AFTER:
            notify.send(f"⚠️ Quelle {name} gestört",
                        f"{e['count']} Läufe in Folge fehlgeschlagen.\n{e['last']}\n"
                        "Die anderen Quellen laufen weiter.", priority=3, tags=("warning",), dry=self.dry)

    def source_ok(self, name: str) -> None:
        e = self.state.errors.pop(name, None)
        if e and e.get("count", 0) >= SOURCE_ALERT_AFTER:
            notify.send(f"✅ Quelle {name} läuft wieder", "", priority=2, dry=self.dry)

    # ---------- Bewertung ----------
    def evaluate(self, fresh: list[Job]) -> list[Job]:
        """Regeln für alle, Details + KI für die besten. Was diesmal nicht drankommt, folgt im nächsten Lauf."""
        home = self.cfg["home"]
        for j in fresh:
            rules.score(j, self.cfg)
        # Entfernung nachschlagen, wo die Quelle keine liefert (nur für Kandidaten, Nominatim ist langsam)
        for j in sorted(fresh, key=lambda x: -x.rule_score):
            if j.distance_km is None and j.location and not j.excluded and j.rule_score >= 3:
                d = self.geo.distance(j.location)
                if d is not None:
                    j.distance_km = d
                    rules.score(j, self.cfg)

        min_rule = self.cfg["ai"]["min_rule_score"]
        candidates = sorted([j for j in fresh if not j.excluded and
                             (j.rule_score >= min_rule or j.category == "ueberfuehrung")],
                            key=lambda x: -x.rule_score)
        postponed = set()
        for i, j in enumerate(candidates):
            if i >= MAX_DETAILS_PER_RUN:
                postponed.add(j.key)
                continue
            try:
                SOURCES[j.source].fetch_details(j)
            except Exception as e:
                log.info("Details für %s nicht ladbar: %s", j.key, e)
            rules.score(j, self.cfg)
            if j.distance_km is not None and j.distance_km > home["radius_km"] + 5:
                j.excluded = f"zu weit ({j.distance_km:.0f} km)"

        to_rate = [j for j in candidates if j.key not in postponed and not j.excluded]
        cap = self.cfg["ai"]["max_jobs_per_run"]
        if self.ai.disabled_reason:
            log.info("KI aus: %s – nur Regel-Bewertung", self.ai.disabled_reason)
        else:
            postponed |= {j.key for j in to_rate[cap:]}
            self.stats["rated"] = self.ai.rate(to_rate[:cap])
            if self.ai.disabled_reason:
                log.info("KI ausgefallen: %s", self.ai.disabled_reason)
        if postponed:
            log.info("%d Kandidaten auf den nächsten Lauf verschoben", len(postponed))
        self.postponed = postponed
        return [j for j in fresh if j.key not in postponed]

    # ---------- Melden ----------
    def notify_jobs(self, jobs: list[Job]) -> None:
        hits = sorted([j for j in jobs if not j.excluded and j.score >= self.push_min], key=lambda x: -x.score)
        digest = [j for j in jobs if not j.excluded and self.cfg["scoring"]["digest_min"] <= j.score < self.push_min]
        self.state.queue.setdefault("digest", []).extend(j.key for j in digest)
        paused, quiet = self.paused(), self.quiet()
        sent = 0
        for j in hits:
            top = j.score >= self.top_min
            if paused or (quiet and not top) or sent >= MAX_PUSHES_PER_RUN:
                self.state.queue.setdefault("morning" if not paused else "digest", []).append(j.key)
                self.state.mark(j, self.now)
                continue
            self.push_job(j, top)
            sent += 1
            self.state.mark(j, self.now, notified=True)
        for j in jobs:
            if j.key not in self.state.seen:
                self.state.mark(j, self.now)

    def push_job(self, j: Job | dict, top: bool) -> None:
        d = j.to_dict() | {"key": j.key} if isinstance(j, Job) else j
        score = report.score_of(d)
        cat = report.CATEGORY_LABEL.get(d.get("category"), "💼 Minijob")
        km = f" ({d['distance_km']:.0f} km)" if d.get("distance_km") is not None else ""
        lines = [d["title"], f"{d.get('company') or '?'} · {d.get('location') or '?'}{km}"]
        if d.get("salary") or d.get("hourly_wage"):
            lines.append("💶 " + (d.get("salary") or f"{d['hourly_wage']:g} €/h".replace(".", ",")))
        lines.append("💬 " + (d.get("ai_reason") or ", ".join(d.get("rule_notes", []))[:160]))
        lines.append(f"Bewerben: /bewerben {d['key']}")
        actions = [notify.view("Anzeige öffnen", d["url"])]
        if config.REPORT_URL:
            actions.append(notify.view("Alle Treffer", config.REPORT_URL))
        pause = notify.command("Pause 8 h", "pause 8")
        if pause:
            actions.append(pause)
        notify.send(f"{'🚨 TOP ' if top else ''}{cat} · {score:.1f}/10", "\n".join(lines),
                    priority=5 if top else 4, tags=("car",) if d.get("category") == "ueberfuehrung" else ("briefcase",),
                    click=d["url"], actions=actions, dry=self.dry)
        self.stats["pushed"] += 1

    def flush_morning_queue(self) -> None:
        """Nachts zurückgehaltene Treffer am Morgen schicken (einzeln bis 3, sonst gesammelt)."""
        queue = self.state.queue.get("morning", [])
        if not queue or self.quiet() or self.paused():
            return
        items = [self.store[k] for k in dict.fromkeys(queue) if k in self.store]
        self.state.queue["morning"] = []
        if len(items) <= 3:
            for d in items:
                self.push_job(d, top=False)
        elif items:
            items.sort(key=lambda d: -report.score_of(d))
            notify.send(f"🌅 {len(items)} neue gute Jobs über Nacht",
                        "\n".join(report.line(d) for d in items[:8]), priority=4, tags=("sunrise",),
                        click=config.REPORT_URL or None, dry=self.dry)
            self.stats["pushed"] += 1

    def maybe_digest(self) -> None:
        today = self.now.date().isoformat()
        if self.now.hour < self.cfg["digest_hour"] or self.state.meta.get("digest_day") == today:
            return
        self.state.meta["digest_day"] = today
        queue = self.state.queue.get("digest", [])
        self.state.queue["digest"] = []
        items = sorted([self.store[k] for k in dict.fromkeys(queue) if k in self.store],
                       key=lambda d: -report.score_of(d))
        if items and not self.paused():
            notify.send(f"📋 Tageszusammenfassung: {len(items)} mittlere Treffer",
                        "\n".join(report.line(d) for d in items[:10]), priority=2, tags=("clipboard",),
                        click=config.REPORT_URL or None, dry=self.dry)

    def maybe_heartbeat(self) -> None:
        week = self.now.strftime("%G-W%V")
        if (self.now.weekday() != self.cfg["heartbeat_weekday"] or self.now.hour < self.cfg["heartbeat_hour"]
                or self.state.meta.get("heartbeat_week") == week):
            return
        self.state.meta["heartbeat_week"] = week
        notify.send("💚 Job-Watcher läuft", self.status_text(), priority=2, tags=("green_heart",),
                    click=config.REPORT_URL or None, dry=self.dry)

    def first_run_summary(self) -> None:
        self.state.meta["heartbeat_week"] = self.now.strftime("%G-W%V")   # kein Lebenszeichen direkt nach dem Start
        good = report.active(self.store, self.now)
        body = [f"{len(self.state.seen)} Anzeigen geprüft, {len(good)} passen grob. Ab jetzt kommen nur neue Treffer.",
                ""] + [report.line(d) for d in good[:6]]
        if self.ai.disabled_reason:
            body.append(f"\nKI-Bewertung aus: {self.ai.disabled_reason}")
        notify.send("🟢 Job-Watcher gestartet", "\n".join(body), priority=3, tags=("rocket",),
                    click=config.REPORT_URL or None, dry=self.dry)

    # ---------- Befehle ----------
    def handle_commands(self) -> None:
        for cmd in control.fetch_commands(self.state):
            log.info("Befehl: %s", cmd)
            reply = control.apply(cmd, self.state, self.cfg, self.now)
            if not reply:
                continue
            title, body = reply
            if title == "status":
                title, body = "ℹ️ Status", self.status_text()
            elif title == "top":
                items = [d for d in report.active(self.store, self.now)][:6]
                title = "🏆 Aktuell beste Jobs"
                body = "\n".join(report.line(d) for d in items) or "Gerade nichts über der Zusammenfassungs-Schwelle."
            notify.send(title, body, priority=3, click=config.REPORT_URL or None, dry=self.dry)

    def status_text(self) -> str:
        m = self.state.meta
        st = m.get("last_stats", {})
        off = self.state.settings.get("sources_off", [])
        lines = [f"Letzter Lauf: {m.get('last_run', 'noch nie')[:16].replace('T', ' ')}",
                 f"Läufe gesamt: {m.get('runs', 0)} · zuletzt {st.get('found', 0)} Anzeigen, "
                 f"{st.get('new', 0)} neu",
                 f"Push ab {self.push_min:g}/10, Top-Alarm ab {self.top_min:g}",
                 f"Aktive Treffer in der Liste: {len(report.active(self.store, self.now))}",
                 f"KI: {'aus – ' + self.ai.disabled_reason if self.ai.disabled_reason else 'Gemini an'}"]
        if self.paused():
            lines.append(f"⏸ Pause bis {self.state.settings['paused_until'][11:16]}")
        if off:
            lines.append("Quellen aus: " + ", ".join(off))
        for name, e in self.state.errors.items():
            lines.append(f"⚠️ {name}: {e['count']}× Fehler ({e.get('last', '')[:60]})")
        return "\n".join(lines)
