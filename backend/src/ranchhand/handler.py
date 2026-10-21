import base64
import json

import boto3
from os import urandom
import time

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

def handler(event, context):
    if event.get("routeKey") == "POST /animals":
        body = parse_body(event)
        dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")
        animal_id = new_ulid()

        item = {
                    "pk": f"ANIMAL#{animal_id}",
                    "sk": "PROFILE",
                    "entity": "animal",
                    "id": animal_id,
                    "number": body['number'],
                    "status": body['status'],
                    "sex": body['sex'],
                    "date_of_birth": body['date_of_birth']
                }

        dynamodb_table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    else:
        return {"statusCode": 404, "headers": {"content-type": "application/json"}, "message": "Route not found"}

