import base64
import json

import boto3
from os import urandom
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
REQUIRED_ANIMAL_FIELDS = ("number", "status", "sex", "date_of_birth")

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

def bad_request(message):
    return {
        "statusCode": 400,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"message": message}),
    }

def create_animal(event):
    """Handle POST /animals: write a new animal profile to the herd table."""
    try:
        body = parse_body(event)
    except ValueError:  # bad JSON, bad base64, or non-UTF-8 bytes
        return bad_request("Request body must be valid JSON")
    if not isinstance(body, dict):
        return bad_request("Request body must be a JSON object")

    missing = [field for field in REQUIRED_ANIMAL_FIELDS if field not in body]
    if missing:
        return bad_request(f"Missing required fields: {', '.join(missing)}")

    dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")
    animal = {
            "id": new_ulid(),
            "number": body['number'],
            "status": body['status'],
            "sex": body['sex'],
            "date_of_birth": body['date_of_birth']
            }

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

