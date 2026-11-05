from unittest.mock import MagicMock, patch

import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_healthz_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_database_down_names_check_without_details(client):
    broken = MagicMock()
    broken.cursor.side_effect = OperationalError("password authentication failed at 10.0.0.5")

    with patch("core.healthz.connection", broken):
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["database"]}
    assert "10.0.0.5" not in response.content.decode()


@pytest.mark.django_db
def test_healthz_valkey_down_names_check_without_details(client):
    broken = MagicMock()
    broken.set.side_effect = ConnectionError("Error connecting to valkey:6379")

    with patch("core.healthz.cache", broken):
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["valkey"]}
    assert "valkey:6379" not in response.content.decode()
