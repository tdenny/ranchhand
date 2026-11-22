import json

import pytest
from helpers import BODY, ULID, api_event, put_animal

from ranchhand import handler as h


def test_create_animal_stores_sire_and_dam_and_omits_blank(table):
    put_animal(table, "SIRE", sex="male")
    body = {**BODY, "sire_id": "SIRE", "dam_id": "  "}
    response = h.handler(api_event(body=json.dumps(body)), None)
    assert response["statusCode"] == 201
    created = json.loads(response["body"])
    assert created["sire_id"] == "SIRE"
    assert created["dam_id"] is None
    item = table.get_item(Key={"pk": f"ANIMAL#{created['id']}", "sk": "PROFILE"})["Item"]
    assert item["sire_id"] == "SIRE"
    assert "dam_id" not in item


def test_create_animal_accepts_existing_sire_and_dam_of_any_status(table):
    put_animal(table, "SIRE", sex="male", status="external", date_of_birth=None)
    put_animal(table, "DAM", sex="female", status="deceased")
    body = {**BODY, "sire_id": "SIRE", "dam_id": "DAM"}

    response = h.handler(api_event(body=json.dumps(body)), None)

    assert response["statusCode"] == 201
    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert (item["sire_id"], item["dam_id"]) == ("SIRE", "DAM")


@pytest.mark.parametrize("field", ["sire_id", "dam_id"])
def test_create_animal_unknown_parent_returns_400_without_writing(table, field):
    response = h.handler(api_event(body=json.dumps({**BODY, field: "NOPE"})), None)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "statusCode": 400,
        "message": "Invalid request",
        "errors": [{"type": "value_error", "loc": ["body", field], "msg": "No animal with id NOPE"}],
    }
    assert table.scan()["Items"] == []


def test_create_animal_free_text_parent_returns_400(table):
    body = {**BODY, "sire_id": "Safe & Sound - Angus Reg# 19705988"}

    assert h.handler(api_event(body=json.dumps(body)), None)["statusCode"] == 400


@pytest.mark.parametrize(
    "field, parent_sex", [("sire_id", "female"), ("dam_id", "male")]
)
def test_create_animal_parent_of_wrong_sex_returns_400_without_writing(table, field, parent_sex):
    put_animal(table, "P", sex=parent_sex)

    response = h.handler(api_event(body=json.dumps({**BODY, field: "P"})), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [(e["loc"], e["msg"]) for e in errors] == [
        (["body", field], f"Animal P is not {'male' if field == 'sire_id' else 'female'}")
    ]
    assert [i["pk"] for i in table.scan()["Items"]] == ["ANIMAL#P"]


def test_create_animal_reports_both_invalid_parents(table):
    body = {**BODY, "sire_id": "X", "dam_id": "Y"}

    response = h.handler(api_event(body=json.dumps(body)), None)

    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["body", "sire_id"], ["body", "dam_id"]]


def test_create_animal_invalid_parent_without_token_returns_401(table):
    event = api_event(body=json.dumps({**BODY, "sire_id": "NOPE"}))
    del event["headers"]["authorization"]

    assert h.handler(event, None)["statusCode"] == 401
