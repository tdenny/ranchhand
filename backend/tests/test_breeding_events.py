import json

import pytest
from botocore.exceptions import ClientError
from helpers import BREEDING_BODY, ULID, api_event, put_animal

from ranchhand import handler as h
from ranchhand import models
from ranchhand.repository import get_repository


def post_breeding(event_type, animal_id=ULID, **fields):
    body = {**BREEDING_BODY, "type": event_type, **fields}
    return h.handler(api_event(f"POST /animals/{animal_id}/breeding-events", body=json.dumps(body)), None)


def profile(table, animal_id=ULID):
    return table.get_item(Key={"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE"})["Item"]


def put_bred_event(table, event_id, date):
    table.put_item(
        Item={
            "pk": f"ANIMAL#{ULID}",
            "sk": f"EVENT#{event_id}",
            "entity": "event",
            "id": event_id,
            "animal_id": ULID,
            "type": "bred",
            "date": date,
            "notes": None,
        }
    )


def errors(response):
    return [(e["loc"], e["msg"]) for e in json.loads(response["body"])["errors"]]


def test_breeding_event_writes_the_event_and_returns_201(table):
    put_animal(table, ULID, breeding_state="unbred")

    response = post_breeding("bred")

    assert response["statusCode"] == 201
    assert response["headers"]["location"] == f"/animals/{ULID}/events/{ULID}"
    assert json.loads(response["body"]) == {
        "id": ULID,
        "animal_id": ULID,
        **BREEDING_BODY,
        "due_date": None,
    }
    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}"})["Item"]
    assert item["type"] == "bred"


@pytest.mark.parametrize("state", ["unbred", "bred", "open"])
def test_bred_event_is_accepted_when_not_pregnant_and_moves_to_bred(table, state):
    put_animal(table, ULID, breeding_state=state)

    assert post_breeding("bred")["statusCode"] == 201
    assert profile(table)["breeding_state"] == "bred"


def test_bred_event_changes_the_category(table):
    put_animal(table, ULID, breeding_state="unbred")
    assert json.loads(h.handler(api_event(f"GET /animals/{ULID}"), None)["body"])["category"] == "Heifer"

    post_breeding("bred")

    assert json.loads(h.handler(api_event(f"GET /animals/{ULID}"), None)["body"])["category"] == "Cow"


def test_confirmed_check_moves_to_pregnant_with_the_given_due_date(table):
    put_animal(table, ULID, breeding_state="bred")

    response = post_breeding("confirmed_pregnant", due_date="2027-03-01")

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["due_date"] == "2027-03-01"
    assert (profile(table)["breeding_state"], profile(table)["due_date"]) == ("pregnant", "2027-03-01")


def test_confirmed_check_defaults_the_due_date_to_283_days_after_the_latest_breeding(table):
    put_animal(table, ULID, breeding_state="bred")
    put_bred_event(table, "B1", "2026-03-01")
    put_bred_event(table, "B2", "2026-04-01")  # 2026-04-01 + 283 days = 2027-01-09
    put_bred_event(table, "B3", "2026-09-01")  # after the check, so not the one that counts

    response = post_breeding("confirmed_pregnant", date="2026-08-01")

    assert json.loads(response["body"])["due_date"] == "2027-01-09"
    assert profile(table)["due_date"] == "2027-01-09"


def test_confirmed_check_without_a_recorded_breeding_leaves_the_due_date_empty(table):
    put_animal(table, ULID, breeding_state="bred")

    response = post_breeding("confirmed_pregnant")

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["due_date"] is None
    assert profile(table)["breeding_state"] == "pregnant"
    assert "due_date" not in profile(table)


def test_open_check_moves_a_bred_cow_to_open(table):
    put_animal(table, ULID, breeding_state="bred")

    response = post_breeding("confirmed_open")

    assert response["statusCode"] == 201
    assert profile(table)["breeding_state"] == "open"
    assert "due_date" not in profile(table)


def test_lost_moves_a_pregnant_cow_to_open_and_clears_the_due_date(table):
    put_animal(table, ULID, breeding_state="pregnant", due_date="2027-02-01")

    assert post_breeding("lost")["statusCode"] == 201
    assert profile(table)["breeding_state"] == "open"
    assert "due_date" not in profile(table)


@pytest.mark.parametrize("state", ["bred", "pregnant"])
def test_calved_moves_to_open_and_clears_the_due_date(table, state):
    put_animal(table, ULID, breeding_state=state, due_date="2027-02-01" if state == "pregnant" else None)

    assert post_breeding("calved")["statusCode"] == 201
    assert profile(table)["breeding_state"] == "open"
    assert "due_date" not in profile(table)


@pytest.mark.parametrize(
    "event_type, states, msg",
    [
        ("bred", ["pregnant"], "Pregnant animals can't be bred"),
        ("confirmed_pregnant", ["unbred", "open", "pregnant"], "Only bred animals can be pregnancy checked"),
        ("confirmed_open", ["unbred", "open", "pregnant"], "Only bred animals can be pregnancy checked"),
        ("calved", ["unbred", "open"], "Only bred or pregnant animals can calve"),
        ("lost", ["unbred", "bred", "open"], "Only pregnant animals can lose a pregnancy"),
    ],
)
def test_breeding_event_in_the_wrong_state_returns_400_without_writing(table, event_type, states, msg):
    for state in states:
        table.delete_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})
        put_animal(table, ULID, breeding_state=state)
        before = table.scan()["Items"]

        response = post_breeding(event_type)

        assert response["statusCode"] == 400
        assert errors(response) == [(["body", "type"], msg)]
        assert table.scan()["Items"] == before


@pytest.mark.parametrize("event_type", ["bred", "confirmed_open", "calved"])
def test_breeding_event_for_a_male_returns_400_without_writing(table, event_type):
    put_animal(table, ULID, sex="male")
    before = table.scan()["Items"]

    response = post_breeding(event_type)

    assert response["statusCode"] == 400
    assert errors(response) == [(["body", "type"], "Only female animals can have breeding events")]
    assert table.scan()["Items"] == before


def test_breeding_event_for_an_unknown_animal_returns_404(table):
    response = post_breeding("bred", animal_id="nope")

    assert response["statusCode"] == 404
    assert table.scan()["Items"] == []


@pytest.mark.parametrize("event_type", ["bred", "confirmed_open", "calved", "lost"])
def test_due_date_on_anything_but_a_confirmed_pregnancy_returns_400_without_writing(table, event_type):
    put_animal(table, ULID, breeding_state="pregnant")
    before = table.scan()["Items"]

    response = post_breeding(event_type, due_date="2027-02-01")

    assert response["statusCode"] == 400
    assert errors(response) == [(["body"], "Value error, due_date is only for a confirmed pregnancy")]
    assert table.scan()["Items"] == before


@pytest.mark.parametrize("event_type", ["preg_checked", "castrated", "weaned", "note", "vaccination", ""])
def test_breeding_event_route_rejects_other_event_types(table, event_type):
    put_animal(table, ULID)

    response = post_breeding(event_type)

    assert response["statusCode"] == 400
    assert [loc for loc, _ in errors(response)] == [["body", "type"]]


def test_breeding_event_requires_token(table):
    event = api_event(f"POST /animals/{ULID}/breeding-events", body=json.dumps(BREEDING_BODY))
    del event["headers"]["authorization"]

    assert h.handler(event, None)["statusCode"] == 401


def test_breeding_events_are_listed_with_the_animals_other_events(table):
    put_animal(table, ULID, breeding_state="bred")
    post_breeding("confirmed_pregnant", due_date="2027-03-01")

    events = json.loads(h.handler(api_event(f"GET /animals/{ULID}/events"), None)["body"])["events"]

    assert [(e["type"], e["due_date"]) for e in events] == [("confirmed_pregnant", "2027-03-01")]


def test_breeding_event_is_refused_if_the_state_changed_since_it_was_read(table):
    put_animal(table, ULID, breeding_state="open")  # the route saw "bred"; the transaction has the last word
    before = table.scan()["Items"]
    event = models.Event(animal_id=ULID, type="calved", date="2024-05-01")

    with pytest.raises(ClientError) as raised:
        get_repository().put_breeding_event(event, frozenset({"bred", "pregnant"}), "open")

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert table.scan()["Items"] == before


def test_breeding_event_with_a_taken_id_changes_nothing(table):
    put_animal(table, ULID, breeding_state="unbred")
    table.put_item(Item={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}", "entity": "event"})  # the id it is about to get
    before = table.scan()["Items"]

    with pytest.raises(ClientError) as raised:
        get_repository().put_breeding_event(models.Event(animal_id=ULID, type="bred", date="2024-05-01"), None, "bred")

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert table.scan()["Items"] == before


def test_breeding_event_for_a_missing_profile_writes_no_event(table):
    with pytest.raises(ClientError) as raised:
        get_repository().put_breeding_event(
            models.Event(animal_id="GONE", type="bred", date="2024-05-01"), None, "bred"
        )

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert table.scan()["Items"] == []


@pytest.fixture
def ids(monkeypatch):
    """Hand out distinct ids (the event first, then the calf), since the cow already has ULID."""
    queue = iter(["EVENT", "CALF"])
    monkeypatch.setattr(models, "new_ulid", lambda: next(queue))


@pytest.mark.parametrize("sex, state", [("male", None), ("female", "unbred")])
def test_calving_with_a_calf_creates_it_in_the_herd(table, ids, sex, state):
    put_animal(table, ULID, number="26", breeding_state="pregnant", due_date="2024-05-01")

    response = post_breeding("calved", calf={"sex": sex})

    assert response["statusCode"] == 201
    assert "calf" not in json.loads(response["body"])
    assert profile(table)["breeding_state"] == "open"
    calf = profile(table, "CALF")
    assert {k: calf.get(k) for k in ("number", "status", "sex", "date_of_birth", "dam_id", "breeding_state")} == {
        "number": "26's calf",
        "status": "active",
        "sex": sex,
        "date_of_birth": "2024-05-01",
        "dam_id": ULID,
        "breeding_state": state,
    }


def test_calving_without_a_calf_creates_none(table, ids):
    put_animal(table, ULID, breeding_state="pregnant", due_date="2024-05-01")

    assert post_breeding("calved")["statusCode"] == 201
    assert len(table.scan()["Items"]) == 2  # the cow and the event


@pytest.mark.parametrize("event_type", ["bred", "confirmed_pregnant", "confirmed_open", "lost"])
def test_calf_on_anything_but_a_calving_returns_400_without_writing(table, event_type):
    put_animal(table, ULID, breeding_state="pregnant")
    before = table.scan()["Items"]

    response = post_breeding(event_type, calf={"sex": "male"})

    assert response["statusCode"] == 400
    assert errors(response) == [(["body"], "Value error, calf is only for a calving")]
    assert table.scan()["Items"] == before


def test_calf_with_an_invalid_sex_returns_400_without_writing(table):
    put_animal(table, ULID, breeding_state="pregnant")
    before = table.scan()["Items"]

    assert post_breeding("calved", calf={"sex": "steer"})["statusCode"] == 400
    assert table.scan()["Items"] == before


def test_a_taken_calf_id_rolls_back_the_calving(table, ids):
    put_animal(table, ULID, breeding_state="pregnant", due_date="2024-05-01")
    put_animal(table, "CALF")
    before = table.scan()["Items"]

    with pytest.raises(ClientError) as raised:
        post_breeding("calved", calf={"sex": "male"})

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert sorted(table.scan()["Items"], key=lambda i: i["pk"]) == sorted(before, key=lambda i: i["pk"])


def test_calving_with_a_calf_of_unknown_sex_creates_it_without_one(table, ids):
    put_animal(table, ULID, number="26", breeding_state="pregnant", due_date="2024-05-01")

    assert post_breeding("calved", date="2026-11-01", calf={})["statusCode"] == 201

    calf = profile(table, "CALF")
    assert "sex" not in calf and "breeding_state" not in calf
    assert calf["number"] == "26's calf"
    assert calf["dam_id"] == ULID
    # Readable, and in the status index (so it is listed).
    body = json.loads(h.handler(api_event("GET /animals/CALF"), None)["body"])
    assert body["sex"] is None and body["category"] == "Calf"
    listed = json.loads(h.handler(api_event("GET /animals"), None)["body"])["animals"]
    assert "CALF" in [a["id"] for a in listed]
