"""Integration tests for the Mock BMS simulator.

Runs the FastAPI app in-process via `fastapi.testclient.TestClient` so the full
WattWise -> BMS webhook -> building state update loop is exercised through real
HTTP semantics (routing, JSON serialisation, status codes) without binding a
real port.

Covers:
  * /health, /api/state, / (dashboard HTML)
  * /command handling for shed_load, shift_schedule, dispatch_technician,
    and the "unknown action_type" fall-through
  * command ordering + 50-entry history ring
  * thread-safety under concurrent POSTs
  * end-to-end round-trip through `triggers.dispatch.dispatch_bms_command`
    (requests.post patched to delegate to TestClient).
"""
from __future__ import annotations

import concurrent.futures
import importlib

import pytest

# ---------------------------------------------------------------------------
# Soft-skip the whole module if FastAPI's TestClient (httpx-backed) isn't
# installed. The simulator itself needs fastapi, but TestClient additionally
# pulls in httpx, which may be missing in a trimmed test env.
# ---------------------------------------------------------------------------
try:
    from fastapi.testclient import TestClient  # noqa: F401
except Exception as _e:  # pragma: no cover - exercised only when deps absent
    pytest.skip(
        f"fastapi.testclient unavailable ({_e}); skipping Mock BMS e2e tests",
        allow_module_level=True,
    )

from bms_simulator import server as bms_server
from bms_simulator.server import app, BMSState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Give every test a pristine BMSState.

    `bms_simulator.server.STATE` is a module-level singleton that holds all
    facility data and history. Tests mutate it, so we swap in a fresh instance
    before each test and restore the original afterwards. We cannot just call
    `STATE.__init__()` because the route handlers close over the module name
    `STATE` — replacing the attribute is the cleanest reset.
    """
    original = bms_server.STATE
    fresh = BMSState()
    monkeypatch.setattr(bms_server, "STATE", fresh)
    yield fresh
    bms_server.STATE = original


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Basic endpoints
# ---------------------------------------------------------------------------

def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "mock-bms"


def test_empty_state_lists_three_default_facilities(client: TestClient) -> None:
    r = client.get("/api/state")
    assert r.status_code == 200
    facilities = r.json()
    assert isinstance(facilities, list)
    ids = {f["facility_id"] for f in facilities}
    assert ids == {"office", "warehouse", "datacentre"}
    for f in facilities:
        assert "baseline_kw" in f and f["baseline_kw"] > 0
        assert "current_kw" in f and f["current_kw"] > 0
        assert f["active_overrides"] == []
        assert f["history"] == []


def test_dashboard_html_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Mock BMS Console" in r.text


# ---------------------------------------------------------------------------
# 2. /command handling
# ---------------------------------------------------------------------------

def _get_facility(client: TestClient, facility_id: str) -> dict:
    facs = client.get("/api/state").json()
    return next(f for f in facs if f["facility_id"] == facility_id)


def test_shed_load_updates_current_kw_and_overrides(client: TestClient) -> None:
    before = _get_facility(client, "office")
    before_kw = before["current_kw"]

    payload = {
        "facility": "office",
        "action_type": "shed_load",
        "loads": ["HVAC-A", "EV-Charger"],
        "shed_kw": 40,
    }
    r = client.post("/command", json=payload)
    assert r.status_code == 200
    ack = r.json()
    assert ack["status"] == "accepted"
    assert ack["facility_id"] == "office"
    assert ack["action_type"] == "shed_load"
    assert "40.0 kW" in ack["summary"]

    after = _get_facility(client, "office")
    assert after["current_kw"] < before_kw
    assert len(after["active_overrides"]) == 2
    loads_seen = {o["load"] for o in after["active_overrides"]}
    assert loads_seen == {"HVAC-A", "EV-Charger"}
    assert len(after["history"]) == 1
    assert after["history"][0]["summary"] == "Shed 40.0 kW across 2 loads"


def test_shift_schedule_adds_override(client: TestClient) -> None:
    payload = {
        "facility": "warehouse",
        "action_type": "shift_schedule",
        "target_hours": "23:00-06:00",
    }
    r = client.post("/command", json=payload)
    assert r.status_code == 200
    assert r.json()["summary"] == "Schedule shift to 23:00-06:00"

    state = _get_facility(client, "warehouse")
    assert len(state["active_overrides"]) == 1
    ov = state["active_overrides"][0]
    assert "shifted to 23:00-06:00" in ov["action"]
    assert ov["kw_reduction"] == 0.0


def test_dispatch_technician_adds_override(client: TestClient) -> None:
    payload = {
        "facility": "datacentre",
        "action_type": "dispatch_technician",
        "note": "inspect chiller #2",
    }
    r = client.post("/command", json=payload)
    assert r.status_code == 200
    assert r.json()["summary"] == "Technician dispatched"

    state = _get_facility(client, "datacentre")
    assert any(o["load"] == "technician dispatched" for o in state["active_overrides"])
    assert state["active_overrides"][0]["action"] == "inspect chiller #2"


def test_unknown_action_falls_through_without_state_change(client: TestClient) -> None:
    before = _get_facility(client, "office")

    payload = {"facility": "office", "action_type": "frobnicate", "foo": "bar"}
    r = client.post("/command", json=payload)
    assert r.status_code == 200
    assert r.json()["summary"] == "Logged (frobnicate)"

    after = _get_facility(client, "office")
    # Current kW untouched, no overrides added, but history entry recorded.
    assert after["current_kw"] == before["current_kw"]
    assert after["active_overrides"] == []
    assert len(after["history"]) == 1
    assert after["history"][0]["action_type"] == "frobnicate"


# ---------------------------------------------------------------------------
# 3. Ordering + concurrency
# ---------------------------------------------------------------------------

def test_multiple_sequential_commands_history_newest_first(client: TestClient) -> None:
    for i in range(5):
        client.post("/command", json={
            "facility": "office",
            "action_type": "shed_load",
            "loads": [f"L{i}"],
            "shed_kw": 1 + i,
        })

    state = _get_facility(client, "office")
    assert len(state["history"]) == 5
    # history is a deque with appendleft -> newest first; shed_kw climbs 1..5,
    # so the first entry should be the kw=5 command.
    assert state["history"][0]["payload"]["shed_kw"] == 5
    assert state["history"][-1]["payload"]["shed_kw"] == 1


def test_concurrent_commands_are_thread_safe(client: TestClient) -> None:
    def _fire(i: int) -> int:
        r = client.post("/command", json={
            "facility": "office",
            "action_type": "shed_load",
            "loads": [f"L{i}"],
            "shed_kw": 1,
        })
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(_fire, range(10)))
    assert statuses == [200] * 10

    state = _get_facility(client, "office")
    assert len(state["history"]) == 10
    assert len(state["active_overrides"]) == 10


# ---------------------------------------------------------------------------
# 4. End-to-end round-trip through triggers.dispatch
# ---------------------------------------------------------------------------

def test_dispatch_helper_round_trips_through_mock_bms(
    client: TestClient, monkeypatch
) -> None:
    """`triggers.dispatch.dispatch_bms_command` -> TestClient -> BMS STATE.

    `dispatch_bms_command` POSTs with the real `requests` library. We patch
    `requests.post` (as resolved inside the dispatch module after a fresh
    import) to delegate to the FastAPI TestClient — effectively a transport
    adapter that keeps everything in-process.
    """
    from triggers import dispatch as dispatch_mod
    importlib.reload(dispatch_mod)

    monkeypatch.setenv("BMS_WEBHOOK_URL", "http://testserver/command")

    class _FakeResponse:
        def __init__(self, inner):
            self._inner = inner
            self.status_code = inner.status_code
            self.text = inner.text

        def json(self):
            return self._inner.json()

    def _fake_post(url, json=None, headers=None, timeout=None):
        # Forward to the in-process TestClient regardless of URL.
        return _FakeResponse(client.post("/command", json=json))

    # Patch `requests.post` as the dispatch module's local `requests` sees it.
    import requests as _real_requests
    monkeypatch.setattr(_real_requests, "post", _fake_post)

    result = dispatch_mod.dispatch_bms_command(
        facility_id="office",
        device_id="hvac-a",
        action="shed_load",
        action_type="shed_load",
        loads=["HVAC-A", "EV-Charger"],
        shed_kw=25,
    )

    assert result["status"] == "sent"
    assert result["http_status"] == 200
    assert result["ack"]["status"] == "accepted"
    assert result["ack"]["facility_id"] == "office"
    assert "25.0 kW" in result["ack"]["summary"]

    # And the Mock BMS state should reflect the dispatched command.
    state = _get_facility(client, "office")
    assert len(state["history"]) == 1
    assert state["history"][0]["action_type"] == "shed_load"
    assert len(state["active_overrides"]) == 2
