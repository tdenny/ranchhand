import json

import pytest
from helpers import ULID, api_event, put_animal

from ranchhand import handler as h

REMOVAL_BODY = {"type": "sold", "date": "2026-11-01", "notes": "to the sale barn"}


def post_removal(event_type, animal_id=ULID, **fields):
    body = {**REMOVAL_BODY, "type": event_type, **fields}
    return h.handler(api_event(f"POST /animals/{animal_id}/removal-events", body=json.dumps(body)), None)


def profile(table, animal_id=ULID):
    return table.get_item(Key={"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE"})["Item"]


def errors(response):
    return [(e["loc"], e["msg"]) for e in json.loads(response["body"])["errors"]]


def test_removal_event_writes_the_event_and_returns_201(table):
    put_animal(table, ULID)

    response = post_removal("sold")

    assert response["statusCode"] == 201
    assert response["headers"]["location"] == f"/animals/{ULID}/events/{ULID}"
    assert json.loads(response["body"]) == {"id": ULID, "animal_id": ULID, **REMOVAL_BODY, "due_date": None}
    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}"})["Item"]
    assert item["type"] == "sold"


@pytest.mark.parametrize("event_type, status", [("sold", "sold"), ("died", "deceased"), ("processed", "processed")])
def test_removal_event_sets_the_status(table, event_type, status):
    put_animal(table, ULID)

    assert post_removal(event_type)["statusCode"] == 201
    assert profile(table)["status"] == status


def test_removed_animal_moves_between_status_listings(table):
    put_animal(table, ULID)
    post_removal("died")

    def listed(status):
        event = api_event("GET /animals", rawQueryString=f"status={status}", queryStringParameters={"status": status})
        return [a["id"] for a in json.loads(h.handler(event, None)["body"])["animals"]]

    assert listed("active") == []
    assert listed("deceased") == [ULID]


def test_removal_event_leaves_the_breeding_state_alone(table):
    put_animal(table, ULID, breeding_state="pregnant", due_date="2027-02-01")

    assert post_removal("sold")["statusCode"] == 201
    assert (profile(table)["breeding_state"], profile(table)["due_date"]) == ("pregnant", "2027-02-01")


def test_removal_event_is_listed_with_the_animals_other_events(table):
    put_animal(table, ULID)
    post_removal("sold")

    response = h.handler(api_event(f"GET /animals/{ULID}/events"), None)

    assert [e["type"] for e in json.loads(response["body"])["events"]] == ["sold"]


@pytest.mark.parametrize("status", ["sold", "deceased", "processed", "external"])
@pytest.mark.parametrize("event_type", ["sold", "died", "processed"])
def test_removal_event_for_an_animal_that_is_not_active_returns_400_without_writing(table, event_type, status):
    put_animal(table, ULID, status=status)
    before = table.scan()["Items"]

    response = post_removal(event_type)

    assert response["statusCode"] == 400
    assert errors(response) == [(["body", "type"], "Only active animals can be removed from the herd")]
    assert table.scan()["Items"] == before


def test_removal_event_for_an_unknown_animal_returns_404(table):
    response = post_removal("sold", animal_id="nope")

    assert response["statusCode"] == 404
    assert table.scan()["Items"] == []


@pytest.mark.parametrize("event_type", ["bred", "castrated", "note", "deceased", "reinstated", ""])
def test_removal_event_route_rejects_other_event_types(table, event_type):
    put_animal(table, ULID)

    response = post_removal(event_type)

    assert response["statusCode"] == 400
    assert [loc for loc, _ in errors(response)] == [["body", "type"]]
    assert profile(table)["status"] == "active"


@pytest.mark.parametrize("route", ["events", "breeding-events"])
@pytest.mark.parametrize("event_type", ["sold", "died", "processed"])
def test_other_event_routes_reject_removal_types(table, route, event_type):
    put_animal(table, ULID)
    body = {**REMOVAL_BODY, "type": event_type}

    response = h.handler(api_event(f"POST /animals/{ULID}/{route}", body=json.dumps(body)), None)

    assert response["statusCode"] == 400
    assert profile(table)["status"] == "active"


def test_removal_event_requires_a_date(table):
    put_animal(table, ULID)

    response = post_removal("sold", date=None)

    assert response["statusCode"] == 400
    assert profile(table)["status"] == "active"


def test_removal_event_requires_token(table):
    event = api_event(f"POST /animals/{ULID}/removal-events", body=json.dumps(REMOVAL_BODY))
    del event["headers"]["authorization"]

    assert h.handler(event, None)["statusCode"] == 401
