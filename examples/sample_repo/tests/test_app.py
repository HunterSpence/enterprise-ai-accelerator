"""
Basic smoke tests for InventoryService.

NOTE: Test coverage is intentionally shallow to demonstrate test_coverage_scanner
findings. Only the happy-path product listing is tested.
"""

import pytest
from app import app, db


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client


def test_list_products_empty(client):
    """GET /api/v1/products should return empty list when no data."""
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
