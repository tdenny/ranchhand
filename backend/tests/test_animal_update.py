import json

from helpers import BODY, ULID, api_event, put_animal

from ranchhand import handler as h


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
