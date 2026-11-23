import json

import pytest
from helpers import BODY, ULID, api_event

from ranchhand import handler as h


def create(**fields):
    return h.handler(api_event(body=json.dumps({**BODY, **fields})), None)


def stored(table):
    return table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]


def test_create_animal_stores_castrated_set_at_creation(table):
    response = create(sex="male", castrated=True)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["castrated"] is True
    assert stored(table)["castrated"] is True


def test_create_female_without_a_breeding_state_is_unbred(table):
    response = create()

    assert json.loads(response["body"])["breeding_state"] == "unbred"
    assert stored(table)["breeding_state"] == "unbred"


def test_create_male_has_no_breeding_state(table):
    response = create(sex="male")

    assert json.loads(response["body"])["breeding_state"] is None
    assert "breeding_state" not in stored(table)


@pytest.mark.parametrize("state", ["unbred", "bred", "open"])
def test_create_animal_stores_breeding_state_set_at_creation(table, state):
    response = create(breeding_state=state)

    assert response["statusCode"] == 201
    assert stored(table)["breeding_state"] == state


def test_create_pregnant_animal_stores_the_due_date(table):
    response = create(breeding_state="pregnant", due_date="2027-02-01")

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["due_date"] == "2027-02-01"
    assert stored(table)["due_date"] == "2027-02-01"


def test_create_pregnant_animal_may_omit_the_due_date(table):
    assert create(breeding_state="pregnant")["statusCode"] == 201
    assert "due_date" not in stored(table)


@pytest.mark.parametrize(
    "fields, msg",
    [
        ({"sex": "female", "castrated": True}, "Only male animals can be castrated"),
        ({"sex": "male", "breeding_state": "bred"}, "Only female animals have a breeding state"),
        ({"breeding_state": "bred", "due_date": "2027-02-01"}, "due_date requires a pregnant animal"),
        ({"due_date": "2027-02-01"}, "due_date requires a pregnant animal"),
    ],
)
def test_create_animal_invalid_flag_combination_returns_400_without_writing(table, fields, msg):
    response = create(**fields)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [(e["loc"], e["msg"]) for e in errors] == [(["body"], f"Value error, {msg}")]
    assert table.scan()["Items"] == []


def test_create_animal_false_castrated_is_accepted_for_either_sex(table):
    assert create(sex="female", castrated=False)["statusCode"] == 201


def test_create_animal_non_boolean_castrated_returns_400(table):
    assert create(sex="male", castrated="maybe")["statusCode"] == 400


def test_create_animal_unknown_breeding_state_returns_400(table):
    assert create(breeding_state="expecting")["statusCode"] == 400
