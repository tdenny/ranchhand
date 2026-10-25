import json

import boto3
import pytest
from moto import mock_aws

from ranchhand import handler as h

BODY = {"number": "101", "status": "active", "sex": "female", "date_of_birth": "2020-04-01"}
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


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
    h.create_animal({"routeKey": "POST /animals", "body": json.dumps(BODY)})

    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert item == {
        "pk": f"ANIMAL#{ULID}",
        "sk": "PROFILE",
        "entity": "animal",
        "id": ULID,
        **BODY,
    }


def test_create_animal_returns_201_with_created_animal(table):
    response = h.create_animal({"routeKey": "POST /animals", "body": json.dumps(BODY)})

    assert response["statusCode"] == 201
    assert response["headers"]["content-type"] == "application/json"
    assert response["headers"]["location"] == f"/animals/{ULID}"
    assert json.loads(response["body"]) == {"id": ULID, **BODY}


@pytest.mark.parametrize(
    "event, message",
    [
        ({"body": "{not json"}, "Request body must be valid JSON"),
        ({"body": "!!!", "isBase64Encoded": True}, "Request body must be valid JSON"),
        ({"body": json.dumps([BODY])}, "Request body must be a JSON object"),
        ({"body": "42"}, "Request body must be a JSON object"),
    ],
)
def test_create_animal_invalid_body_returns_400_without_writing(table, event, message):
    response = h.create_animal(event)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {"message": message}
    assert table.scan()["Items"] == []


def test_create_animal_missing_field_returns_400_without_writing(table):
    body = {k: v for k, v in BODY.items() if k not in ("sex", "status")}

    response = h.create_animal({"body": json.dumps(body)})

    assert response["statusCode"] == 400
    assert response["headers"]["content-type"] == "application/json"
    assert json.loads(response["body"]) == {
        "message": "Invalid animal",
        "errors": [
            {"type": "missing", "loc": ["status"], "msg": "Field required"},
            {"type": "missing", "loc": ["sex"], "msg": "Field required"},
        ],
    }
    assert table.scan()["Items"] == []


def test_create_animal_invalid_date_of_birth_returns_400_without_writing(table):
    response = h.create_animal({"body": json.dumps({**BODY, "date_of_birth": "last spring"})})

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["date_of_birth"]]
    assert table.scan()["Items"] == []
