import json

from fastapi.testclient import TestClient

from kasauti.server import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["serpapi"] is True      # offline mode counts as available
    assert body["offline"] is True
    assert body["mode"] == "rule-based"


def test_examples_endpoint():
    res = client.get("/api/examples")
    assert res.status_code == 200
    examples = res.json()
    assert isinstance(examples, list) and examples
    assert {"name", "text"} <= set(examples[0].keys())


def test_index_served():
    res = client.get("/")
    assert res.status_code == 200
    assert "KASAUTI" in res.text


def test_check_streams_events_then_report():
    payload = {
        "text": "UNESCO has declared our national anthem the BEST in the world! "
                "Forward to every Indian!",
        "offline": True,
    }
    with client.stream("POST", "/api/check", json=payload) as res:
        assert res.status_code == 200
        lines = [json.loads(l) for l in res.iter_lines() if l.strip()]
    kinds = [l["type"] for l in lines]
    assert "event" in kinds
    assert kinds[-1] == "report"
    report = lines[-1]["report"]
    assert report["overall_label"] == "false"
    assert report["searches_used"] == 3
    assert report["suggested_reply"]


def test_check_empty_input_errors_gracefully():
    with client.stream("POST", "/api/check", json={"text": "", "offline": True}) as res:
        lines = [json.loads(l) for l in res.iter_lines() if l.strip()]
    assert lines[-1]["type"] == "error"
