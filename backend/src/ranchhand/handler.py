import base64
import json

import boto3
from os import urandom
import time

from pydantic import ValidationError

from ranchhand.models import AnimalIn

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def new_ulid(now_ms=None):
    """48-bit millisecond timestamp + 80 random bits, as 26 sortable characters."""
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    n = (ts << 80) | int.from_bytes(urandom(10), "big")
    return "".join(_ALPHABET[(n >> (5 * i)) & 31] for i in reversed(range(26)))


def parse_body(event):
    """Decode the JSON request body from an API Gateway HTTP API (v2) event."""
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    return json.loads(body)

def bad_request(message, **extra):
    return {
        "statusCode": 400,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"message": message, **extra}),
    }

def create_animal(event):
    """Handle POST /animals: write a new animal profile to the herd table."""
    try:
        body = parse_body(event)
    except ValueError:  # bad JSON, bad base64, or non-UTF-8 bytes
        return bad_request("Request body must be valid JSON")
    if not isinstance(body, dict):
        return bad_request("Request body must be a JSON object")

    try:
        animal_in = AnimalIn.model_validate(body)
    except ValidationError as e:
        return bad_request("Invalid animal", errors=e.errors(include_url=False, include_context=False, include_input=False))

    dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")
    animal = {"id": new_ulid(), **animal_in.model_dump(mode="json")}

    db_record = {
        "pk": f"ANIMAL#{animal['id']}",
        "sk": "PROFILE",
        "entity": "animal",
        **animal,
    }

    dynamodb_table.put_item(Item=db_record, ConditionExpression="attribute_not_exists(pk)")

    return {
        "statusCode": 201,
        "headers": {
            "content-type": "application/json",
            "location": f"/animals/{animal['id']}",
        },
        "body": json.dumps(animal)
    }

def handler(event, context):
    if event.get("routeKey") == "POST /animals":
        return create_animal(event)
    else:
        return {"statusCode": 404, "headers": {"content-type": "application/json"}, "message": "Route not found"}

