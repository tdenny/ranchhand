import json

import pytest
from helpers import BODY, TOKEN, api_event

from ranchhand import handler as h
from ranchhand import routes
from ranchhand.repository import get_repository


def test_get_repository_is_shared_until_cleared(table):
    assert get_repository() is get_repository()

    first = get_repository()
    get_repository.cache_clear()

    assert get_repository() is not first


def test_unknown_route_returns_404():
    response = h.handler(api_event("GET /nope"), None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"])["message"] == "Not found"


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Bearer", "Bearer wrong", "Bearer tøken", TOKEN, f"Basic {TOKEN}", f"Bearer {TOKEN} extra"],
)
def test_bad_authorization_returns_401_without_writing(table, authorization):
    event = api_event(body=json.dumps(BODY))
    event["headers"].pop("authorization")
    if authorization is not None:
        event["headers"]["authorization"] = authorization

    response = h.handler(event, None)

    assert response["statusCode"] == 401
    assert response["headers"]["WWW-Authenticate"] == "Bearer"
    assert json.loads(response["body"])["message"] == "Unauthorized"
    assert table.scan()["Items"] == []


def test_invalid_body_without_token_returns_401_not_400(table):
    event = api_event(body="{not json")
    del event["headers"]["authorization"]

    assert h.handler(event, None)["statusCode"] == 401


@pytest.mark.parametrize("value", [None, ""])
def test_unset_api_token_rejects_everything(table, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("API_TOKEN")
    else:
        monkeypatch.setenv("API_TOKEN", value)

    for header in ("Bearer ", "Bearer"):
        event = api_event(body=json.dumps(BODY))
        event["headers"]["authorization"] = header
        assert h.handler(event, None)["statusCode"] == 401


def test_authorization_header_name_is_case_insensitive(table):
    event = api_event(body=json.dumps(BODY))
    event["headers"] = {"Authorization": f"bearer {TOKEN}"}

    assert h.handler(event, None)["statusCode"] == 201


ORIGIN = "http://localhost:8000"


@pytest.fixture
def cors_origin(monkeypatch):
    monkeypatch.setattr(routes.cors_config, "_allowed_origins", [ORIGIN])


def test_preflight_succeeds_without_token(cors_origin):
    event = api_event(
        "OPTIONS /animals",
        headers={
            "origin": ORIGIN,
            "access-control-request-method": "GET",
            "access-control-request-headers": "authorization",
        },
    )

    response = h.handler(event, None)

    assert response["statusCode"] == 204
    assert response["headers"]["Access-Control-Allow-Origin"] == ORIGIN
    assert "Authorization" in response["headers"]["Access-Control-Allow-Headers"]


def test_unauthorized_response_carries_cors_headers(cors_origin):
    event = api_event("GET /animals", headers={"origin": ORIGIN})

    response = h.handler(event, None)

    assert response["statusCode"] == 401
    assert response["headers"]["Access-Control-Allow-Origin"] == ORIGIN


def test_list_animals_response_carries_cors_headers(table, cors_origin):
    event = api_event("GET /animals")
    event["headers"]["origin"] = ORIGIN

    response = h.handler(event, None)

    assert response["statusCode"] == 200
    assert response["headers"]["Access-Control-Allow-Origin"] == ORIGIN
