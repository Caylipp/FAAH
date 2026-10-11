"""Befehlszeile.

  python -m jobwatcher run [--state-dir DIR] [--dry]   ein Lauf (GitHub Actions oder lokal)
  python -m jobwatcher test-push                         Test-Push an NTFY_TOPIC
  python -m jobwatcher show [--state-dir DIR]            aktuelle Trefferliste im Terminal
"""
import argparse
import logging
import sys
import time
from pathlib import Path

from . import config, notify, report
from .runner import Runner


def main() -> None:
    p = argparse.ArgumentParser(prog="jobwatcher")
    p.add_argument("command", choices=["run", "test-push", "show"])
    p.add_argument("--state-dir", type=Path, default=config.ROOT / ".state")
    p.add_argument("--dry", action="store_true", help="keine Pushes senden, nur ins Log schreiben")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if a.command == "test-push":
        if not config.NTFY_TOPIC:
            sys.exit("NTFY_TOPIC fehlt (Secret bzw. .env)")
        ok = notify.send("✅ Job-Watcher Test", "Wenn du das liest, kommen Pushes an.", priority=3,
                         tags=("white_check_mark",), click=config.REPORT_URL or None)
        sys.exit(0 if ok else 1)
    if a.command == "show":
        runner = Runner(a.state_dir, dry=True)
        for d in report.active(runner.store, runner.now):
            print(report.line(d), "\n   ", d["url"], "\n   ", d.get("ai_reason") or ", ".join(d["rule_notes"]))
        return
    try:
        Runner(a.state_dir, dry=a.dry).run()
    except Exception as e:
        logging.exception("Lauf abgebrochen")
        _alert_once(a.state_dir, f"{type(e).__name__}: {e}"[:400], a.dry)
        raise


def _alert_once(state_dir: Path, msg: str, dry: bool) -> None:
    """Denselben Absturz höchstens alle 12 Stunden melden, sonst kommt alle 30 Minuten ein Push."""
    marker = state_dir / "last_error.txt"
    now = time.time()
    try:
        old_msg, old_ts = marker.read_text(encoding="utf-8").split("\n", 1)[1], marker.stat().st_mtime
        if old_msg == msg and now - old_ts < 12 * 3600:
            return
    except (FileNotFoundError, IndexError):
        pass
    state_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{int(now)}\n{msg}", encoding="utf-8")
    notify.send("❌ Job-Watcher Fehler", msg, priority=3, tags=("x",), dry=dry)
