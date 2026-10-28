import json

import boto3
import pytest
from moto import mock_aws

from ranchhand import handler as h

BODY = {"number": "101", "status": "active", "sex": "female", "date_of_birth": "2020-04-01"}
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def api_event(route_key="POST /animals", **fields):
    """A minimal API Gateway HTTP API (v2) event; fields (e.g. body) are merged in."""
    method, path = route_key.split(" ")
    return {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
        "isBase64Encoded": False,
        **fields,
    }


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(h, "new_ulid", lambda: ULID)
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
    assert json.loads(response["body"]) == {"id": ULID, **BODY}


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
    # Powertools validation alone would silently create an animal from the first element.
    response = h.handler(api_event(body=json.dumps([BODY, BODY])), None)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {"statusCode": 400, "message": "Request body must be a JSON object"}
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
        {"id": "0", **BODY},
        {"id": "1", **other},
    ]


def test_list_animals_empty_herd_returns_empty_list(table):
    response = h.handler(api_event("GET /animals"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"animals": []}
