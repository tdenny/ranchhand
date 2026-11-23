import json

import pytest
from helpers import BODY, CATEGORY, EVENT_BODY, FLAGS_UNSET, PARENTS_UNSET, ULID, api_event, put_animal

from ranchhand import handler as h
from ranchhand import routes
from ranchhand.repository import HerdRepository


def test_list_animals_returns_all_animals(table):
    other = {**BODY, "number": "102"}
    for i, body in enumerate((BODY, other)):
        table.put_item(Item={"pk": f"ANIMAL#{i}", "sk": "PROFILE", "entity": "animal", "id": str(i), **body})
    table.put_item(Item={"pk": "OTHER#1", "sk": "PROFILE", "entity": "other"})

    response = h.handler(api_event("GET /animals"), None)

    assert response["statusCode"] == 200
    assert sorted(json.loads(response["body"])["animals"], key=lambda a: a["id"]) == [
        {"id": "0", **BODY, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY},
        {"id": "1", **other, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY},
    ]


def test_get_animal_returns_animal(table):
    table.put_item(Item={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID, **BODY})

    response = h.handler(api_event(f"GET /animals/{ULID}"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"id": ULID, **BODY, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY}


def test_get_animal_unknown_id_returns_404(table):
    response = h.handler(api_event(f"GET /animals/{ULID}"), None)

    assert response["statusCode"] == 404


def test_list_animals_empty_herd_returns_empty_list(table):
    response = h.handler(api_event("GET /animals"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"animals": []}


def test_list_animals_omits_table_attributes(table):
    table.put_item(Item={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID, **BODY})

    response = h.handler(api_event("GET /animals"), None)

    assert json.loads(response["body"]) == {
        "animals": [{"id": ULID, **BODY, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY}]
    }


def generate_get_animals_api_event(*statuses):
    """GET /animals as API Gateway HTTP API (v2) sends repeated parameters: comma-joined."""
    event = api_event("GET /animals")
    if statuses:
        event["rawQueryString"] = "&".join(f"status={s}" for s in statuses)
        event["queryStringParameters"] = {"status": ",".join(statuses)}
    return event


def numbers_from_api_response(event):
    response = h.handler(event, None)
    assert response["statusCode"] == 200
    return [a["number"] for a in json.loads(response["body"])["animals"]]


@pytest.fixture
def mixed_herd(table):
    put_animal(table, "A", number="3", status="active")
    put_animal(table, "B", number="1", status="sold")
    put_animal(table, "C", number="2", status="deceased")
    put_animal(table, "D", number="4", status="external", date_of_birth=None)
    return table


def test_list_animals_without_status_excludes_external_and_sorts_by_number(mixed_herd):
    assert numbers_from_api_response(generate_get_animals_api_event()) == ["1", "2", "3"]


def test_list_animals_filters_by_single_status(mixed_herd):
    assert numbers_from_api_response(generate_get_animals_api_event("sold")) == ["1"]


def test_list_animals_filters_by_multiple_statuses_sorted_by_number(mixed_herd):
    assert numbers_from_api_response(generate_get_animals_api_event("active", "sold")) == ["1", "3"]


def test_list_animals_external_status_is_opt_in(mixed_herd):
    assert numbers_from_api_response(generate_get_animals_api_event("external")) == ["4"]
    assert numbers_from_api_response(generate_get_animals_api_event("active", "external")) == ["3", "4"]


def test_list_animals_duplicate_statuses_do_not_duplicate_animals(mixed_herd):
    assert numbers_from_api_response(generate_get_animals_api_event("active", "active")) == ["3"]


def test_list_animals_unknown_status_returns_400(mixed_herd):
    response = h.handler(generate_get_animals_api_event("archived"), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"][:2] for e in errors] == [["query", "status"]]


def test_list_animals_status_filter_ignores_events(table):
    put_animal(table, ULID)
    h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps(EVENT_BODY)), None)

    assert numbers_from_api_response(generate_get_animals_api_event("active")) == ["101"]


def test_list_animals_pages_through_each_status(table, monkeypatch):
    for i in range(3):
        put_animal(table, str(i), number=str(i))
    real_query = table.query
    monkeypatch.setattr(table, "query", lambda **kw: real_query(**kw, Limit=1))
    monkeypatch.setattr(routes, "get_repository", lambda: HerdRepository(table))

    assert numbers_from_api_response(generate_get_animals_api_event("active")) == ["0", "1", "2"]
