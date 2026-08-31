import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Allow `from app...` imports when pytest is run from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    """Fresh, isolated DB per test.

    Drops all tables before the app's lifespan runs, so `main.py`'s own
    startup logic (create_all + seed two warehouses) does the setup — the
    seeded warehouses always come out as id=1 (Paris warehouse) and
    id=2 (Lyon warehouse) since the tables are recreated empty each time.
    """
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)

@pytest.fixture()
def product(client):
    """A product with reorder_threshold=10 and no stock yet."""
    response = client.post(
        "/products",
        json={"sku": "WIDGET-1", "name": "Widget", "unit_price": 9.99, "reorder_threshold": 10},
    )
    assert response.status_code == 201
    return response.json()

@pytest.fixture()
def show():
    """Pretty-prints a response's status and JSON body.

    pytest hides stdout for passing tests by default — run with `-s` to
    actually see this output (e.g. `pytest -s -v tests/test_stock_transfers.py`).
    """
    def _show(label, response):
        print(f"\n{label}: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except ValueError:
            print(response.text)
    return _show