import json

import pytest
from botocore.exceptions import ClientError
from helpers import BODY, EVENT_BODY, EVENT_UNSET, ULID, api_event, put_animal

from ranchhand import handler as h
from ranchhand import models
from ranchhand.repository import get_repository


def test_create_animal_event_writes_event_item(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps(EVENT_BODY)), None)

    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}"})["Item"]
    assert item == {
        "pk": f"ANIMAL#{ULID}",
        "sk": f"EVENT#{ULID}",
        "entity": "event",
        "id": ULID,
        "animal_id": ULID,
        **EVENT_BODY,
        **EVENT_UNSET,
    }


def test_create_animal_event_returns_201(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    response = h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps(EVENT_BODY)), None)

    assert response["statusCode"] == 201
    assert response["headers"]["location"] == f"/animals/{ULID}/events/{ULID}"
    assert json.loads(response["body"]) == {"id": ULID, "animal_id": ULID, **EVENT_BODY, **EVENT_UNSET}


def test_create_animal_event_unknown_animal_returns_404(table):
    response = h.handler(api_event("POST /animals/nope/events", body=json.dumps(EVENT_BODY)), None)

    assert response["statusCode"] == 404
    assert table.scan()["Items"] == []


def test_create_animal_event_invalid_body_returns_400(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    response = h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps({"type": "x"})), None)

    assert response["statusCode"] == 400


@pytest.mark.parametrize("event_type", ["castrated", "weaned", "note"])
def test_create_animal_event_accepts_each_type(table, event_type):
    put_animal(table, ULID, sex="male")
    body = {**EVENT_BODY, "type": event_type}

    response = h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps(body)), None)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["type"] == event_type


# Breeding events have their own route, so this one can't change a breeding state.
@pytest.mark.parametrize(
    "event_type",
    ["vaccination", "Note", "", "castrate", "bred", "confirmed_pregnant", "confirmed_open", "calved", "lost"],
)
def test_create_animal_event_unknown_type_returns_400_without_writing(table, event_type):
    h.handler(api_event(body=json.dumps(BODY)), None)
    body = {**EVENT_BODY, "type": event_type}

    response = h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps(body)), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["body", "type"]]
    assert [i["sk"] for i in table.scan()["Items"]] == ["PROFILE"]


def put_event(table, animal_id, event_id, **fields):
    table.put_item(
        Item={
            "pk": f"ANIMAL#{animal_id}",
            "sk": f"EVENT#{event_id}",
            "entity": "event",
            "id": event_id,
            "animal_id": animal_id,
            **{**EVENT_BODY, **fields},
        }
    )


def test_list_animal_events_returns_events_newest_first(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    put_event(table, ULID, "01ARZ3NDEKTSV4RRFFQ69G5FA1", type="note")
    put_event(table, ULID, "01ARZ3NDEKTSV4RRFFQ69G5FA3", type="calved")
    put_event(table, ULID, "01ARZ3NDEKTSV4RRFFQ69G5FA2", type="bred")

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
        **{**EVENT_BODY, "type": "calved"},
        **EVENT_UNSET,
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


def profile(table, animal_id=ULID):
    return table.get_item(Key={"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE"})["Item"]


def create_milestone_event(event_type, animal_id=ULID):
    body = {**EVENT_BODY, "type": event_type}
    return h.handler(api_event(f"POST /animals/{animal_id}/events", body=json.dumps(body)), None)


def test_castrated_event_writes_event_and_sets_flag(table):
    put_animal(table, ULID, sex="male")

    response = create_milestone_event("castrated")

    assert response["statusCode"] == 201
    assert profile(table)["castrated"] is True
    event = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}"})["Item"]
    assert event["type"] == "castrated"


def test_castrated_event_changes_the_category(table):
    put_animal(table, ULID, sex="male")
    assert json.loads(h.handler(api_event(f"GET /animals/{ULID}"), None)["body"])["category"] == "Bull"

    create_milestone_event("castrated")

    assert json.loads(h.handler(api_event(f"GET /animals/{ULID}"), None)["body"])["category"] == "Steer"


def test_castrated_event_for_an_already_castrated_animal_keeps_the_flag(table):
    put_animal(table, ULID, sex="male", castrated=True)

    response = create_milestone_event("castrated")

    assert response["statusCode"] == 201
    assert profile(table)["castrated"] is True


def test_castrated_event_for_a_female_returns_400_without_writing(table):
    put_animal(table, ULID, sex="female")
    before = table.scan()["Items"]

    response = create_milestone_event("castrated")

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [(e["loc"], e["msg"]) for e in errors] == [(["body", "type"], "Only male animals can be castrated")]
    assert table.scan()["Items"] == before


@pytest.mark.parametrize("sex", ["female", "male"])
@pytest.mark.parametrize("event_type", ["weaned", "note"])
def test_non_milestone_events_apply_to_either_sex_and_leave_the_profile_alone(table, sex, event_type):
    put_animal(table, ULID, sex=sex)
    before = profile(table)

    response = create_milestone_event(event_type)

    assert response["statusCode"] == 201
    assert profile(table) == before


def test_milestone_event_with_a_taken_id_changes_nothing(table):
    put_animal(table, ULID, sex="male")
    put_event(table, ULID, ULID, type="note")  # the id the new event is about to get
    before = table.scan()["Items"]

    with pytest.raises(ClientError) as raised:
        get_repository().put_event(models.Event(animal_id=ULID, **{**EVENT_BODY, "type": "castrated"}))

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert table.scan()["Items"] == before


def test_milestone_event_for_a_missing_profile_writes_no_event(table):
    with pytest.raises(ClientError) as raised:
        get_repository().put_event(models.Event(animal_id="GONE", **{**EVENT_BODY, "type": "castrated"}))

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert table.scan()["Items"] == []
