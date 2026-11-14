import json

import boto3
import pytest
from moto import mock_aws

from ranchhand import handler as h
from ranchhand import models, routes

BODY = {"number": "101", "status": "active", "sex": "female", "date_of_birth": "2020-04-01"}
PARENTS_UNSET = {"sire_id": None, "dam_id": None}
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
TOKEN = "test-token"


@pytest.fixture(autouse=True)
def api_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)


def api_event(route_key="POST /animals", **fields):
    """A minimal API Gateway HTTP API (v2) event; fields (e.g. body) are merged in."""
    method, path = route_key.split(" ")
    return {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json", "authorization": f"Bearer {TOKEN}"},
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
        "isBase64Encoded": False,
        **fields,
    }


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(models, "new_ulid", lambda: ULID)
    with mock_aws():
        yield boto3.resource("dynamodb").create_table(
            TableName="ranchhand-herd",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )


def test_create_animal_writes_profile_item(table):
    h.handler(api_event(body=json.dumps(BODY)), None)

    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert item == {
        "pk": f"ANIMAL#{ULID}",
        "sk": "PROFILE",
        "entity": "animal",
        "id": ULID,
        **BODY,
    }


def test_create_animal_returns_201_with_created_animal(table):
    response = h.handler(api_event(body=json.dumps(BODY)), None)

    assert response["statusCode"] == 201
    assert response["headers"]["Content-Type"] == "application/json"
    assert response["headers"]["location"] == f"/animals/{ULID}"
    assert json.loads(response["body"]) == {"id": ULID, **BODY, **PARENTS_UNSET}


@pytest.mark.parametrize(
    "fields, error_type",
    [
        ({"body": "{not json"}, "json_invalid"),
        ({"body": "!!!", "isBase64Encoded": True}, "missing"),
        ({"body": "42"}, "model_attributes_type"),
        ({"body": json.dumps([1])}, "model_attributes_type"),
        ({}, "missing"),
    ],
)
def test_create_animal_invalid_body_returns_400_without_writing(table, fields, error_type):
    response = h.handler(api_event(**fields), None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["message"] == "Invalid request"
    assert [e["type"] for e in body["errors"]] == [error_type]
    assert table.scan()["Items"] == []


def test_create_animal_array_body_returns_400_without_writing(table):
    # This basically tests that Powertools works as expected, but
    # Powertools < 3.38 silently created an animal from the first element.
    response = h.handler(api_event(body=json.dumps([BODY, BODY])), None)

    assert response["statusCode"] == 400
    assert json.loads(response["body"])["errors"][0]["type"] == "model_attributes_type"
    assert table.scan()["Items"] == []


def test_create_animal_missing_field_returns_400_without_writing(table):
    body = {k: v for k, v in BODY.items() if k not in ("sex", "status")}

    response = h.handler(api_event(body=json.dumps(body)), None)

    assert response["statusCode"] == 400
    assert response["headers"]["Content-Type"] == "application/json"
    assert json.loads(response["body"]) == {
        "statusCode": 400,
        "message": "Invalid request",
        "errors": [
            {"type": "missing", "loc": ["body", "status"], "msg": "Field required"},
            {"type": "missing", "loc": ["body", "sex"], "msg": "Field required"},
        ],
    }
    assert table.scan()["Items"] == []


@pytest.mark.parametrize("status", ["Active", "archived", "", None])
def test_create_animal_invalid_status_returns_400_without_writing(table, status):
    response = h.handler(api_event(body=json.dumps({**BODY, "status": status})), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["body", "status"]]
    assert table.scan()["Items"] == []


@pytest.mark.parametrize("status", ["active", "deceased", "processed", "sold"])
def test_create_animal_accepts_each_status(table, status):
    response = h.handler(api_event(body=json.dumps({**BODY, "status": status})), None)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["status"] == status


def test_create_animal_invalid_date_of_birth_returns_400_without_writing(table):
    response = h.handler(api_event(body=json.dumps({**BODY, "date_of_birth": "last spring"})), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["body", "date_of_birth"]]
    assert table.scan()["Items"] == []


def test_unknown_route_returns_404():
    response = h.handler(api_event("GET /nope"), None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"])["message"] == "Not found"


def test_list_animals_returns_all_animals(table):
    other = {**BODY, "number": "102"}
    for i, body in enumerate((BODY, other)):
        table.put_item(
            Item={"pk": f"ANIMAL#{i}", "sk": "PROFILE", "entity": "animal", "id": str(i), **body}
        )
    table.put_item(Item={"pk": "OTHER#1", "sk": "PROFILE", "entity": "other"})

    response = h.handler(api_event("GET /animals"), None)

    assert response["statusCode"] == 200
    assert sorted(json.loads(response["body"])["animals"], key=lambda a: a["id"]) == [
        {"id": "0", **BODY, **PARENTS_UNSET},
        {"id": "1", **other, **PARENTS_UNSET},
    ]


def test_get_animal_returns_animal(table):
    table.put_item(
        Item={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID, **BODY}
    )

    response = h.handler(api_event(f"GET /animals/{ULID}"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"id": ULID, **BODY, **PARENTS_UNSET}


def test_get_animal_unknown_id_returns_404(table):
    response = h.handler(api_event(f"GET /animals/{ULID}"), None)

    assert response["statusCode"] == 404


def test_list_animals_empty_herd_returns_empty_list(table):
    response = h.handler(api_event("GET /animals"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"animals": []}



def test_list_animals_omits_table_attributes(table):
    table.put_item(
        Item={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID, **BODY}
    )

    response = h.handler(api_event("GET /animals"), None)

    assert json.loads(response["body"]) == {"animals": [{"id": ULID, **BODY, **PARENTS_UNSET}]}


EVENT_BODY = {"type": "vaccination", "date": "2024-05-01", "notes": "annual booster"}


def test_create_animal_event_writes_event_item(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    h.handler(api_event("POST /animals/{}/events".format(ULID), body=json.dumps(EVENT_BODY)), None)

    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}"})["Item"]
    assert item == {
        "pk": f"ANIMAL#{ULID}",
        "sk": f"EVENT#{ULID}",
        "entity": "event",
        "id": ULID,
        "animal_id": ULID,
        **EVENT_BODY,
    }


def test_create_animal_event_returns_201(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    response = h.handler(
        api_event(f"POST /animals/{ULID}/events", body=json.dumps(EVENT_BODY)), None
    )

    assert response["statusCode"] == 201
    assert response["headers"]["location"] == f"/animals/{ULID}/events/{ULID}"
    assert json.loads(response["body"]) == {"id": ULID, "animal_id": ULID, **EVENT_BODY}


def test_create_animal_event_unknown_animal_returns_404(table):
    response = h.handler(
        api_event("POST /animals/nope/events", body=json.dumps(EVENT_BODY)), None
    )

    assert response["statusCode"] == 404
    assert table.scan()["Items"] == []


def test_create_animal_event_invalid_body_returns_400(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    response = h.handler(
        api_event(f"POST /animals/{ULID}/events", body=json.dumps({"type": "x"})), None
    )

    assert response["statusCode"] == 400


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
    event = api_event("OPTIONS /animals", headers={
        "origin": ORIGIN,
        "access-control-request-method": "GET",
        "access-control-request-headers": "authorization",
    })

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


def put_event(table, animal_id, event_id, **fields):
    table.put_item(Item={
        "pk": f"ANIMAL#{animal_id}",
        "sk": f"EVENT#{event_id}",
        "entity": "event",
        "id": event_id,
        "animal_id": animal_id,
        **{**EVENT_BODY, **fields},
    })


def test_list_animal_events_returns_events_newest_first(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    put_event(table, ULID, "01ARZ3NDEKTSV4RRFFQ69G5FA1", type="vaccination")
    put_event(table, ULID, "01ARZ3NDEKTSV4RRFFQ69G5FA3", type="weighing")
    put_event(table, ULID, "01ARZ3NDEKTSV4RRFFQ69G5FA2", type="treatment")

    response = h.handler(api_event(f"GET /animals/{ULID}/events"), None)

    assert response["statusCode"] == 200
    events = json.loads(response["body"])["events"]
    assert [e["id"] for e in events] == [
        "01ARZ3NDEKTSV4RRFFQ69G5FA3",
        "01ARZ3NDEKTSV4RRFFQ69G5FA2",
        "01ARZ3NDEKTSV4RRFFQ69G5FA1",
    ]
    assert events[0] == {
        "id": "01ARZ3NDEKTSV4RRFFQ69G5FA3",
        "animal_id": ULID,
        **{**EVENT_BODY, "type": "weighing"},
    }


def test_list_animal_events_omits_profile_and_other_animals_events(table):
    other = "01ARZ3NDEKTSV4RRFFQ69G5FAW"
    h.handler(api_event(body=json.dumps(BODY)), None)
    put_event(table, ULID, "01ARZ3NDEKTSV4RRFFQ69G5FA1")
    put_event(table, other, "01ARZ3NDEKTSV4RRFFQ69G5FA2")

    response = h.handler(api_event(f"GET /animals/{ULID}/events"), None)

    events = json.loads(response["body"])["events"]
    assert [e["id"] for e in events] == ["01ARZ3NDEKTSV4RRFFQ69G5FA1"]


def test_list_animal_events_without_events_returns_empty_list(table):
    h.handler(api_event(body=json.dumps(BODY)), None)

    response = h.handler(api_event(f"GET /animals/{ULID}/events"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"events": []}


def test_list_animal_events_unknown_animal_returns_404(table):
    response = h.handler(api_event(f"GET /animals/{ULID}/events"), None)

    assert response["statusCode"] == 404


def test_list_animal_events_requires_token(table):
    event = api_event(f"GET /animals/{ULID}/events")
    del event["headers"]["authorization"]

    assert h.handler(event, None)["statusCode"] == 401


def test_create_animal_stores_sire_and_dam_and_omits_blank(table):
    body = {**BODY, "sire_id": "01SIRE", "dam_id": "  "}
    response = h.handler(api_event(body=json.dumps(body)), None)
    assert response["statusCode"] == 201
    created = json.loads(response["body"])
    assert created["sire_id"] == "01SIRE"
    assert created["dam_id"] is None
    item = table.get_item(Key={"pk": f"ANIMAL#{created['id']}", "sk": "PROFILE"})["Item"]
    assert item["sire_id"] == "01SIRE"
    assert "dam_id" not in item


def test_create_animal_accepts_animal_id_or_free_text_parents(table):
    sire = "Safe & Sound - Angus Reg# 19705988"
    body = {**BODY, "sire_id": sire, "dam_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}
    response = h.handler(api_event(body=json.dumps(body)), None)
    assert response["statusCode"] == 201
    created = json.loads(response["body"])
    assert (created["sire_id"], created["dam_id"]) == (sire, "01ARZ3NDEKTSV4RRFFQ69G5FAV")
    item = table.get_item(Key={"pk": f"ANIMAL#{created['id']}", "sk": "PROFILE"})["Item"]
    assert (item["sire_id"], item["dam_id"]) == (sire, "01ARZ3NDEKTSV4RRFFQ69G5FAV")
