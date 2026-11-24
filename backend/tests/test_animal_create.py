import json

import pytest
from helpers import BODY, CATEGORY, FLAGS_UNSET, PARENTS_UNSET, TODAY, ULID, api_event

from ranchhand import handler as h


def test_create_animal_writes_profile_item(table):
    h.handler(api_event(body=json.dumps(BODY)), None)

    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert item == {
        "pk": f"ANIMAL#{ULID}",
        "sk": "PROFILE",
        "entity": "animal",
        "id": ULID,
        **BODY,
        "castrated": False,
        "breeding_state": "unbred",
    }


def test_create_animal_returns_201_with_created_animal(table):
    response = h.handler(api_event(body=json.dumps(BODY)), None)

    assert response["statusCode"] == 201
    assert response["headers"]["Content-Type"] == "application/json"
    assert response["headers"]["location"] == f"/animals/{ULID}"
    assert json.loads(response["body"]) == {"id": ULID, **BODY, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY}


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


@pytest.mark.parametrize("status", ["active", "deceased", "processed", "sold", "external"])
def test_create_animal_accepts_each_status(table, status):
    response = h.handler(api_event(body=json.dumps({**BODY, "status": status})), None)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["status"] == status


@pytest.mark.parametrize("sex", ["Female", "cow", "", None])
def test_create_animal_invalid_sex_returns_400_without_writing(table, sex):
    response = h.handler(api_event(body=json.dumps({**BODY, "sex": sex})), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["body", "sex"]]
    assert table.scan()["Items"] == []


@pytest.mark.parametrize("sex", ["female", "male"])
def test_create_animal_accepts_each_sex(table, sex):
    response = h.handler(api_event(body=json.dumps({**BODY, "sex": sex})), None)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["sex"] == sex


@pytest.mark.parametrize("status", ["active", "deceased", "processed", "sold"])
@pytest.mark.parametrize("missing", ["omitted", "null"])
def test_create_animal_missing_date_of_birth_returns_400_unless_external(table, status, missing):
    body = {**BODY, "status": status}
    del body["date_of_birth"]
    if missing == "null":
        body["date_of_birth"] = None

    response = h.handler(api_event(body=json.dumps(body)), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [(e["loc"], e["msg"]) for e in errors] == [
        (["body"], "Value error, date_of_birth is required for animals that are not external")
    ]
    assert table.scan()["Items"] == []


@pytest.mark.parametrize("missing", ["omitted", "null"])
def test_create_external_animal_without_date_of_birth_omits_attribute(table, missing):
    body = {"number": "Black Jack", "status": "external", "sex": "male"}
    if missing == "null":
        body["date_of_birth"] = None

    response = h.handler(api_event(body=json.dumps(body)), None)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["date_of_birth"] is None
    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert "date_of_birth" not in item


def test_get_external_animal_without_date_of_birth(table):
    h.handler(api_event(body=json.dumps({"number": "Black Jack", "status": "external", "sex": "male"})), None)

    response = h.handler(api_event(f"GET /animals/{ULID}"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["date_of_birth"] is None


def test_create_animal_invalid_date_of_birth_returns_400_without_writing(table):
    response = h.handler(api_event(body=json.dumps({**BODY, "date_of_birth": "last spring"})), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["body", "date_of_birth"]]
    assert table.scan()["Items"] == []


def test_calf_of_unknown_sex_is_called_a_calf():
    from ranchhand.models import Animal

    calf = Animal(number="26's calf", status="active", date_of_birth=TODAY, dam_id="D")
    assert calf.category == "Calf"
    adult = Animal(number="9", status="active", date_of_birth="2010-01-01")
    assert adult.category is None
