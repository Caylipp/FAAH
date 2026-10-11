import json

from jobwatcher import ai
from jobwatcher.config import load_config
from jobwatcher.models import Job

CFG = load_config()


class Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        return self._payload


def answer(items):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(items)}]}}]})


def jobs(n):
    return [Job(source="ba", source_id=str(i), title=f"Job {i}", url="u") for i in range(n)]


def test_rates_in_batches(monkeypatch):
    calls = []

    def post(url, json, timeout, headers):
        n = json["contents"][0]["parts"][0]["text"].count("--- id:")
        calls.append(url)
        return answer([{"id": str(i), "score": 8, "reason": "passt"} for i in range(n)])

    monkeypatch.setattr(ai.requests, "post", post)
    js = jobs(10)
    g = ai.Gemini("key", ["m1"], CFG)
    assert g.rate(js) == 10
    assert len(calls) == 2 and all(j.ai_score == 8 for j in js)


def test_model_fallback_on_404(monkeypatch):
    seen = []

    def post(url, json, timeout, headers):
        seen.append(url)
        return Resp(404, {}, "not found") if "/m1:" in url else answer([{"id": "0", "score": 3, "reason": "x"}])

    monkeypatch.setattr(ai.requests, "post", post)
    js = jobs(1)
    ai.Gemini("key", ["m1", "m2"], CFG).rate(js)
    assert js[0].ai_score == 3 and "/m2:" in seen[-1]


def test_quota_exhausted_disables(monkeypatch):
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: Resp(429, {}, "quota"))
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)
    g = ai.Gemini("key", ["m1"], CFG)
    js = jobs(3)
    assert g.rate(js) == 0
    assert "429" in g.disabled_reason and js[0].ai_score is None
