import pytest
from fastapi.testclient import TestClient

from app.main import app, failure_state, orders


@pytest.fixture()
def client():
    failure_state.update(active=False, kind=None, started_at=None)
    orders.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    # Skip real sleeps in latency simulation during tests
    import time as _time
    orig = _time.sleep
    monkeypatch.setattr(_time, "sleep", lambda s: orig(min(s, 0.05)))
