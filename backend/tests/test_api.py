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
    "fields, message",
    [
        ({"body": "{not json"}, "Request body must be valid JSON"),
        ({"body": "!!!", "isBase64Encoded": True}, "Request body must be a JSON object"),
        ({"body": json.dumps([BODY])}, "Request body must be a JSON object"),
        ({"body": "42"}, "Request body must be a JSON object"),
        ({}, "Request body must be a JSON object"),
    ],
)
def test_create_animal_invalid_body_returns_400_without_writing(table, fields, message):
    response = h.handler(api_event(**fields), None)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {"statusCode": 400, "message": message}
    assert table.scan()["Items"] == []


def test_create_animal_missing_field_returns_400_without_writing(table):
    body = {k: v for k, v in BODY.items() if k not in ("sex", "status")}

    response = h.handler(api_event(body=json.dumps(body)), None)

    assert response["statusCode"] == 400
    assert response["headers"]["Content-Type"] == "application/json"
    assert json.loads(response["body"]) == {
        "statusCode": 400,
        "message": "Invalid animal",
        "errors": [
            {"type": "missing", "loc": ["status"], "msg": "Field required"},
            {"type": "missing", "loc": ["sex"], "msg": "Field required"},
        ],
    }
    assert table.scan()["Items"] == []


def test_create_animal_invalid_date_of_birth_returns_400_without_writing(table):
    response = h.handler(api_event(body=json.dumps({**BODY, "date_of_birth": "last spring"})), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["date_of_birth"]]
    assert table.scan()["Items"] == []


def test_unknown_route_returns_404():
    response = h.handler(api_event("GET /nope"), None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"])["message"] == "Not found"
