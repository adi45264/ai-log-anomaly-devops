import pytest
from fastapi.testclient import TestClient

from log_platform.detector import detector
from log_platform.main import app, incidents


@pytest.fixture()
def client():
    detector.clear()
    incidents.clear()
    with TestClient(app) as c:
        yield c
