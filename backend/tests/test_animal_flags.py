import json

import pytest
from helpers import BODY, ULID, api_event

from ranchhand import handler as h


@pytest.mark.parametrize(
    "sex, flag", [("male", "castrated"), ("female", "bred")]
)
def test_create_animal_stores_milestone_flag_set_at_creation(table, sex, flag):
    body = {**BODY, "sex": sex, flag: True}

    response = h.handler(api_event(body=json.dumps(body)), None)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])[flag] is True
    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert item[flag] is True


@pytest.mark.parametrize(
    "sex, flag, msg",
    [
        ("female", "castrated", "Only male animals can be castrated"),
        ("male", "bred", "Only female animals can be bred"),
    ],
)
def test_create_animal_flag_for_wrong_sex_returns_400_without_writing(table, sex, flag, msg):
    response = h.handler(api_event(body=json.dumps({**BODY, "sex": sex, flag: True})), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [(e["loc"], e["msg"]) for e in errors] == [(["body"], f"Value error, {msg}")]
    assert table.scan()["Items"] == []


@pytest.mark.parametrize("sex, flag", [("female", "castrated"), ("male", "bred")])
def test_create_animal_false_flag_is_accepted_for_either_sex(table, sex, flag):
    response = h.handler(api_event(body=json.dumps({**BODY, "sex": sex, flag: False})), None)

    assert response["statusCode"] == 201


def test_create_animal_non_boolean_flag_returns_400(table):
    body = {**BODY, "sex": "male", "castrated": "maybe"}

    assert h.handler(api_event(body=json.dumps(body)), None)["statusCode"] == 400


def test_legacy_item_without_flags_reads_as_not_castrated_or_bred(table):
    table.put_item(Item={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID, **BODY})

    response = h.handler(api_event(f"GET /animals/{ULID}"), None)

    animal = json.loads(response["body"])
    assert (animal["castrated"], animal["bred"]) == (False, False)
