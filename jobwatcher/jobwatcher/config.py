"""Konfiguration: config.yaml (was gesucht wird) + Umgebungsvariablen (Geheimnisse)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Berlin")
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


def _load_dotenv() -> None:
    """Lokal (Mac): .env einlesen. In GitHub Actions kommen die Werte aus den Secrets."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or ROOT / "config.yaml").read_text(encoding="utf-8"))


NTFY_SERVER = env("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = env("NTFY_TOPIC")
CONTROL_TOPIC = env("NTFY_CONTROL_TOPIC")
GEMINI_API_KEY = env("GEMINI_API_KEY")
# Link in den Pushes auf die Trefferliste (TREFFER.md im State-Branch)
REPORT_URL = env("REPORT_URL")
