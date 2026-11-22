import json
from datetime import date

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from ranchhand import handler as h
from ranchhand import models, routes
from ranchhand.repository import HerdRepository, get_repository

BODY = {"number": "101", "status": "active", "sex": "female", "date_of_birth": "2020-04-01"}
PARENTS_UNSET = {"sire_id": None, "dam_id": None}
FLAGS_UNSET = {"castrated": False, "bred": False}
TODAY = date(2026, 11, 21)
# What BODY (a cow-aged female not yet bred) is called on TODAY.
CATEGORY = {"category": "Heifer"}
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
TOKEN = "test-token"


@pytest.fixture(autouse=True)
def api_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(models, "today", lambda: TODAY)


def api_event(route_key="POST /animals", **fields):
    """A minimal API Gateway HTTP API (v2) event; fields (e.g. body) are merged in."""
    method, path = route_key.split(" ")
    return {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json", "authorization": f"Bearer {TOKEN}"},
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
        "isBase64Encoded": False,
        **fields,
    }


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(models, "new_ulid", lambda: ULID)
    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="ranchhand-herd",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": a, "AttributeType": "S"}
                for a in ("pk", "sk", "number", "status", "date_of_birth", "sire_id", "dam_id")
            ],
            # Mirrors infra/dynamodb.tf.
            GlobalSecondaryIndexes=[
                {
                    "IndexName": name,
                    "KeySchema": [
                        {"AttributeName": hash_key, "KeyType": "HASH"},
                        {"AttributeName": range_key, "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
                for name, hash_key, range_key in (
                    ("number-index", "number", "pk"),
                    ("status-index", "status", "number"),
                    ("sire-index", "sire_id", "date_of_birth"),
                    ("dam-index", "dam_id", "date_of_birth"),
                )
            ],
        )
        # The repository is cached for warm Lambdas; make sure it binds to this test's table.
        get_repository.cache_clear()
        try:
            yield table
        finally:
            get_repository.cache_clear()


def test_create_animal_writes_profile_item(table):
    h.handler(api_event(body=json.dumps(BODY)), None)

    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert item == {
        "pk": f"ANIMAL#{ULID}",
        "sk": "PROFILE",
        "entity": "animal",
        "id": ULID,
        **BODY,
        **FLAGS_UNSET,
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


def test_get_repository_is_shared_until_cleared(table):
    assert get_repository() is get_repository()

    first = get_repository()
    get_repository.cache_clear()

    assert get_repository() is not first


def test_unknown_route_returns_404():
    response = h.handler(api_event("GET /nope"), None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"])["message"] == "Not found"


def test_list_animals_returns_all_animals(table):
    other = {**BODY, "number": "102"}
    for i, body in enumerate((BODY, other)):
        table.put_item(
            Item={"pk": f"ANIMAL#{i}", "sk": "PROFILE", "entity": "animal", "id": str(i), **body}
        )
    table.put_item(Item={"pk": "OTHER#1", "sk": "PROFILE", "entity": "other"})

    response = h.handler(api_event("GET /animals"), None)

    assert response["statusCode"] == 200
    assert sorted(json.loads(response["body"])["animals"], key=lambda a: a["id"]) == [
        {"id": "0", **BODY, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY},
        {"id": "1", **other, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY},
    ]


def test_get_animal_returns_animal(table):
    table.put_item(
        Item={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID, **BODY}
    )

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
    table.put_item(
        Item={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID, **BODY}
    )

    response = h.handler(api_event("GET /animals"), None)

    assert json.loads(response["body"]) == {"animals": [{"id": ULID, **BODY, **PARENTS_UNSET, **FLAGS_UNSET, **CATEGORY}]}


def put_animal(table, animal_id, **fields):
    """Store an animal; a field set to None is left out (as the API does for unset values)."""
    item = {"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE", "entity": "animal", "id": animal_id, **BODY, **fields}
    table.put_item(Item={k: v for k, v in item.items() if v is not None})


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


EVENT_BODY = {"type": "note", "date": "2024-05-01", "notes": "annual booster"}


def test_create_animal_event_writes_event_item(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    h.handler(api_event("POST /animals/{}/events".format(ULID), body=json.dumps(EVENT_BODY)), None)

    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}"})["Item"]
    assert item == {
        "pk": f"ANIMAL#{ULID}",
        "sk": f"EVENT#{ULID}",
        "entity": "event",
        "id": ULID,
        "animal_id": ULID,
        **EVENT_BODY,
    }


def test_create_animal_event_returns_201(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    response = h.handler(
        api_event(f"POST /animals/{ULID}/events", body=json.dumps(EVENT_BODY)), None
    )

    assert response["statusCode"] == 201
    assert response["headers"]["location"] == f"/animals/{ULID}/events/{ULID}"
    assert json.loads(response["body"]) == {"id": ULID, "animal_id": ULID, **EVENT_BODY}


def test_create_animal_event_unknown_animal_returns_404(table):
    response = h.handler(
        api_event("POST /animals/nope/events", body=json.dumps(EVENT_BODY)), None
    )

    assert response["statusCode"] == 404
    assert table.scan()["Items"] == []


def test_create_animal_event_invalid_body_returns_400(table):
    h.handler(api_event(body=json.dumps(BODY)), None)
    response = h.handler(
        api_event(f"POST /animals/{ULID}/events", body=json.dumps({"type": "x"})), None
    )

    assert response["statusCode"] == 400


@pytest.mark.parametrize("event_type", ["castrated", "bred", "calved", "weaned", "note"])
def test_create_animal_event_accepts_each_type(table, event_type):
    put_animal(table, ULID, sex="male" if event_type == "castrated" else "female")
    body = {**EVENT_BODY, "type": event_type}

    response = h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps(body)), None)

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["type"] == event_type


@pytest.mark.parametrize("event_type", ["vaccination", "Note", "", "castrate"])
def test_create_animal_event_unknown_type_returns_400_without_writing(table, event_type):
    h.handler(api_event(body=json.dumps(BODY)), None)
    body = {**EVENT_BODY, "type": event_type}

    response = h.handler(api_event(f"POST /animals/{ULID}/events", body=json.dumps(body)), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [e["loc"] for e in errors] == [["body", "type"]]
    assert [i["sk"] for i in table.scan()["Items"]] == ["PROFILE"]


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Bearer", "Bearer wrong", "Bearer tøken", TOKEN, f"Basic {TOKEN}", f"Bearer {TOKEN} extra"],
)
def test_bad_authorization_returns_401_without_writing(table, authorization):
    event = api_event(body=json.dumps(BODY))
    event["headers"].pop("authorization")
    if authorization is not None:
        event["headers"]["authorization"] = authorization

    response = h.handler(event, None)

    assert response["statusCode"] == 401
    assert response["headers"]["WWW-Authenticate"] == "Bearer"
    assert json.loads(response["body"])["message"] == "Unauthorized"
    assert table.scan()["Items"] == []


def test_invalid_body_without_token_returns_401_not_400(table):
    event = api_event(body="{not json")
    del event["headers"]["authorization"]

    assert h.handler(event, None)["statusCode"] == 401


@pytest.mark.parametrize("value", [None, ""])
def test_unset_api_token_rejects_everything(table, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("API_TOKEN")
    else:
        monkeypatch.setenv("API_TOKEN", value)

    for header in ("Bearer ", "Bearer"):
        event = api_event(body=json.dumps(BODY))
        event["headers"]["authorization"] = header
        assert h.handler(event, None)["statusCode"] == 401


def test_authorization_header_name_is_case_insensitive(table):
    event = api_event(body=json.dumps(BODY))
    event["headers"] = {"Authorization": f"bearer {TOKEN}"}

    assert h.handler(event, None)["statusCode"] == 201


ORIGIN = "http://localhost:8000"


@pytest.fixture
def cors_origin(monkeypatch):
    monkeypatch.setattr(routes.cors_config, "_allowed_origins", [ORIGIN])


def test_preflight_succeeds_without_token(cors_origin):
    event = api_event("OPTIONS /animals", headers={
        "origin": ORIGIN,
        "access-control-request-method": "GET",
        "access-control-request-headers": "authorization",
    })

    response = h.handler(event, None)

    assert response["statusCode"] == 204
    assert response["headers"]["Access-Control-Allow-Origin"] == ORIGIN
    assert "Authorization" in response["headers"]["Access-Control-Allow-Headers"]


def test_unauthorized_response_carries_cors_headers(cors_origin):
    event = api_event("GET /animals", headers={"origin": ORIGIN})

    response = h.handler(event, None)

    assert response["statusCode"] == 401
    assert response["headers"]["Access-Control-Allow-Origin"] == ORIGIN


def test_list_animals_response_carries_cors_headers(table, cors_origin):
    event = api_event("GET /animals")
    event["headers"]["origin"] = ORIGIN

    response = h.handler(event, None)

    assert response["statusCode"] == 200
    assert response["headers"]["Access-Control-Allow-Origin"] == ORIGIN


def put_event(table, animal_id, event_id, **fields):
    table.put_item(Item={
        "pk": f"ANIMAL#{animal_id}",
        "sk": f"EVENT#{event_id}",
        "entity": "event",
        "id": event_id,
        "animal_id": animal_id,
        **{**EVENT_BODY, **fields},
    })


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


def profile(table, animal_id=ULID):
    return table.get_item(Key={"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE"})["Item"]


def create_milestone_event(event_type, animal_id=ULID):
    body = {**EVENT_BODY, "type": event_type}
    return h.handler(api_event(f"POST /animals/{animal_id}/events", body=json.dumps(body)), None)


@pytest.mark.parametrize(
    "sex, event_type, flag",
    [("male", "castrated", "castrated"), ("female", "bred", "bred"), ("female", "calved", "bred")],
)
def test_milestone_event_writes_event_and_sets_flag(table, sex, event_type, flag):
    put_animal(table, ULID, sex=sex)

    response = create_milestone_event(event_type)

    assert response["statusCode"] == 201
    assert profile(table)[flag] is True
    event = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": f"EVENT#{ULID}"})["Item"]
    assert event["type"] == event_type


def test_milestone_event_sets_only_its_own_flag(table):
    put_animal(table, ULID, sex="female")

    create_milestone_event("calved")

    item = profile(table)
    assert item["bred"] is True
    assert "castrated" not in item


def test_milestone_event_changes_the_category(table):
    put_animal(table, ULID, sex="male")
    assert json.loads(h.handler(api_event(f"GET /animals/{ULID}"), None)["body"])["category"] == "Bull"

    create_milestone_event("castrated")

    assert json.loads(h.handler(api_event(f"GET /animals/{ULID}"), None)["body"])["category"] == "Steer"


def test_milestone_event_for_an_already_flagged_animal_keeps_the_flag(table):
    put_animal(table, ULID, sex="male", castrated=True)

    response = create_milestone_event("castrated")

    assert response["statusCode"] == 201
    assert profile(table)["castrated"] is True


@pytest.mark.parametrize(
    "sex, event_type, msg",
    [
        ("female", "castrated", "Only male animals can be castrated"),
        ("male", "bred", "Only female animals can be bred"),
        ("male", "calved", "Only female animals can calve"),
    ],
)
def test_milestone_event_for_the_wrong_sex_returns_400_without_writing(table, sex, event_type, msg):
    put_animal(table, ULID, sex=sex)
    before = table.scan()["Items"]

    response = create_milestone_event(event_type)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [(e["loc"], e["msg"]) for e in errors] == [(["body", "type"], msg)]
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
    put_animal(table, ULID, sex="female")
    put_event(table, ULID, ULID, type="note")  # the id the new event is about to get
    before = table.scan()["Items"]

    with pytest.raises(ClientError) as raised:
        get_repository().put_event(models.Event(animal_id=ULID, **{**EVENT_BODY, "type": "bred"}))

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert table.scan()["Items"] == before


def test_milestone_event_for_a_missing_profile_writes_no_event(table):
    with pytest.raises(ClientError) as raised:
        get_repository().put_event(models.Event(animal_id="GONE", **{**EVENT_BODY, "type": "castrated"}))

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert table.scan()["Items"] == []


# --- PUT /animals/<id> ---

def put_event_item(table, animal_id, event_id):
    table.put_item(
        Item={"pk": f"ANIMAL#{animal_id}", "sk": f"EVENT#{event_id}", "entity": "event", "id": event_id,
              "animal_id": animal_id, "type": "note", "date": "2024-01-01"}
    )


def update_event(animal_id, body):
    return api_event(f"PUT /animals/{animal_id}", body=json.dumps(body))


def test_update_animal_replaces_every_field_and_returns_it(table):
    put_animal(table, ULID, sire_id="OLDSIRE", dam_id="OLDDAM")
    put_animal(table, "SIRE", sex="male", number="1")
    new = {"number": "102", "status": "sold", "sex": "male", "date_of_birth": "2021-05-06",
           "sire_id": "SIRE", "castrated": True, "bred": False}

    response = h.handler(update_event(ULID, new), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {
        "id": ULID, **new, "dam_id": None, "category": "Steer"
    }
    item = table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "PROFILE"})["Item"]
    assert item == {"pk": f"ANIMAL#{ULID}", "sk": "PROFILE", "entity": "animal", "id": ULID,
                    **{k: v for k, v in new.items()}}  # the cleared dam_id is gone, not null


def test_update_animal_keeps_events(table):
    put_animal(table, ULID)
    put_event_item(table, ULID, "E1")

    h.handler(update_event(ULID, {**BODY, "number": "999"}), None)

    assert table.get_item(Key={"pk": f"ANIMAL#{ULID}", "sk": "EVENT#E1"}).get("Item") is not None


def test_update_unknown_animal_returns_404_without_writing(table):
    response = h.handler(update_event(ULID, BODY), None)

    assert response["statusCode"] == 404
    assert table.scan()["Items"] == []


def test_update_animal_invalid_body_returns_400_without_changing_it(table):
    put_animal(table, ULID)
    before = table.scan()["Items"]

    response = h.handler(update_event(ULID, {**BODY, "date_of_birth": None}), None)

    assert response["statusCode"] == 400
    assert table.scan()["Items"] == before


def test_update_animal_rejects_itself_as_a_parent(table):
    put_animal(table, ULID, sex="male")

    response = h.handler(update_event(ULID, {**BODY, "sex": "male", "sire_id": ULID}), None)

    assert response["statusCode"] == 400
    errors = json.loads(response["body"])["errors"]
    assert [(e["loc"], e["msg"]) for e in errors] == [(["body", "sire_id"], "An animal cannot be its own parent")]


def test_update_animal_rejects_parent_of_wrong_sex_or_missing(table):
    put_animal(table, ULID)
    put_animal(table, "COW", sex="female", number="2")

    response = h.handler(update_event(ULID, {**BODY, "sire_id": "COW", "dam_id": "NOPE"}), None)

    assert response["statusCode"] == 400
    assert [e["loc"] for e in json.loads(response["body"])["errors"]] == [["body", "sire_id"], ["body", "dam_id"]]


def test_update_animal_requires_the_token(table):
    put_animal(table, ULID)
    event = update_event(ULID, BODY)
    event["headers"].pop("authorization")

    assert h.handler(event, None)["statusCode"] == 401
