from datetime import date

TODAY = date(2026, 11, 21)
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
TOKEN = "test-token"

BODY = {"number": "101", "status": "active", "sex": "female", "date_of_birth": "2020-04-01"}
PARENTS_UNSET = {"sire_id": None, "dam_id": None}
FLAGS_UNSET = {"castrated": False, "breeding_state": "unbred", "due_date": None}
# What BODY (a cow-aged female not yet bred) is called on TODAY.
CATEGORY = {"category": "Heifer"}
EVENT_BODY = {"type": "note", "date": "2024-05-01", "notes": "annual booster"}
EVENT_UNSET = {"due_date": None}
BREEDING_BODY = {"type": "bred", "date": "2024-05-01", "notes": "AI"}


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


def put_animal(table, animal_id, **fields):
    """Store an animal; a field set to None is left out (as the API does for unset values)."""
    item = {"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE", "entity": "animal", "id": animal_id, **BODY, **fields}
    table.put_item(Item={k: v for k, v in item.items() if v is not None})
