"""Ablauf mit Fake-Quellen: Erststart still, danach Push nur für neue gute Treffer, Ruhezeit, Befehle."""
from datetime import datetime

import pytest

from jobwatcher import config, notify, runner as runner_mod
from jobwatcher.models import Job

GOOD = dict(title="Fahrer für Fahrzeugüberführungen (m/w/d) Minijob",
            snippet="Einsätze am Wochenende, flexibel, 15 €/Std.", distance_km=10)


class FakeSource:
    def __init__(self):
        self.jobs = []
        self.fail = False

    def search(self, cfg, home):
        if self.fail:
            raise RuntimeError("kaputt")
        return [Job(**j) for j in self.jobs]

    def fetch_details(self, job):
        pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    src = FakeSource()
    monkeypatch.setattr(runner_mod, "SOURCES", {"ba": src})
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "NTFY_TOPIC", "")
    monkeypatch.setattr(config, "CONTROL_TOPIC", "")
    notify.SENT.clear()
    return src, tmp_path


def run(tmp, when="2026-10-11T12:00"):
    r = runner_mod.Runner(tmp, now=datetime.fromisoformat(when).replace(tzinfo=config.TZ))
    r.run()
    return r


def add(src, n, **kw):
    src.jobs.append(dict(source="ba", source_id=str(n), url=f"https://x/{n}", company=f"Firma {n}", **(GOOD | kw)))


def test_first_run_silent_then_new_hit_pushed(env):
    src, tmp = env
    add(src, 1)
    run(tmp)
    assert [m["title"] for m in notify.SENT] == ["🟢 Job-Watcher gestartet"]
    notify.SENT.clear()
    run(tmp)                                   # nichts Neues
    assert notify.SENT == []
    add(src, 2, title="Überführungsfahrer Minijob Sonntag")
    run(tmp)
    assert len(notify.SENT) == 1 and "TOP" in notify.SENT[0]["title"]
    assert "/bewerben ba:2" in notify.SENT[0]["message"]
    assert (tmp / "TREFFER.md").read_text().count("### ") == 2


def test_quiet_hours_hold_normal_hits_until_morning(env, monkeypatch):
    src, tmp = env
    run(tmp)
    notify.SENT.clear()
    add(src, 3, title="Fahrer Minijob Autohaus", snippet="", distance_km=20)   # gut, aber kein Top
    r = run(tmp, "2026-10-11T23:30")
    hit = r.store["ba:3"]
    assert 7 <= hit["rule_score"] < 8.5
    assert notify.SENT == []
    run(tmp, "2026-10-12T07:30")
    assert len(notify.SENT) == 1


def test_duplicate_on_other_portal_not_pushed_twice(env):
    src, tmp = env
    run(tmp)
    add(src, 4)
    run(tmp)
    notify.SENT.clear()
    src.jobs.append(dict(source="ba", source_id="other", url="u2", company="Firma 4", **GOOD))
    run(tmp)
    assert notify.SENT == []


def test_source_failure_alert_after_six_runs(env):
    src, tmp = env
    run(tmp)
    src.fail = True
    notify.SENT.clear()
    for _ in range(6):
        run(tmp)
    assert [m["title"] for m in notify.SENT] == ["⚠️ Quelle ba gestört"]
    src.fail = False
    run(tmp)
    assert notify.SENT[-1]["title"] == "✅ Quelle ba läuft wieder"


def test_commands(env, monkeypatch):
    src, tmp = env
    run(tmp)
    cmds = iter([["pause 2"], ["schwelle 9.5"], ["status"]])
    monkeypatch.setattr(runner_mod.control, "fetch_commands", lambda state: next(cmds, []))
    notify.SENT.clear()
    add(src, 5)
    run(tmp)                                   # pausiert: kein Treffer-Push, nur Bestätigung
    assert [m["title"] for m in notify.SENT] == ["⏸ Pause"]
    r = run(tmp)
    assert r.push_min == 9.5
    run(tmp)
    assert notify.SENT[-1]["title"] == "ℹ️ Status"
