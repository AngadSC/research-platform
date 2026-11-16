import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from core import weather


class _Resp:
    status_code = 200

    def json(self):
        return {
            "timezone": "America/Edmonton",
            "current": {"temperature_2m": -1.4, "weather_code": 71},
        }


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()


@pytest.mark.django_db
def test_weather_needs_a_signed_in_person():
    assert APIClient().get("/api/weather/?lat=53.5&lon=-113.5").status_code in (401, 403)


@pytest.mark.django_db
def test_weather_without_coordinates_says_nothing_is_available(make_user):
    c = APIClient()
    c.force_authenticate(make_user())
    assert c.get("/api/weather/").json() == {"available": False}
    assert c.get("/api/weather/?lat=999&lon=0").json() == {"available": False}
    assert c.get("/api/weather/?lat=x&lon=y").json() == {"available": False}


@pytest.mark.django_db
def test_weather_rounds_the_spot_and_caches_the_answer(make_user, monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        return _Resp()

    monkeypatch.setattr(weather.requests, "get", fake_get)
    c = APIClient()
    c.force_authenticate(make_user())
    first = c.get("/api/weather/?lat=53.5461&lon=-113.4938").json()
    assert first == {"available": True, "temperature_c": -1, "code": 71, "place": "Edmonton"}
    c.get("/api/weather/?lat=53.5499&lon=-113.4999")  # the same 10 km square
    assert len(calls) == 1
    assert calls[0]["latitude"] == 53.5 and calls[0]["longitude"] == -113.5


@pytest.mark.django_db
def test_weather_failure_is_not_an_error(make_user, monkeypatch):
    def boom(url, params, timeout):
        raise weather.requests.ConnectionError

    monkeypatch.setattr(weather.requests, "get", boom)
    c = APIClient()
    c.force_authenticate(make_user())
    assert c.get("/api/weather/?lat=1&lon=1").json() == {"available": False}
