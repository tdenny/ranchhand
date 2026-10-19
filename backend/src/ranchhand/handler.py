import boto3
from os import urandom
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def new_ulid(now_ms=None):
    """48-bit millisecond timestamp + 80 random bits, as 26 sortable characters."""
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    n = (ts << 80) | int.from_bytes(urandom(10), "big")
    return "".join(_ALPHABET[(n >> (5 * i)) & 31] for i in reversed(range(26)))

def handler(event, context):
    if event.get("routeKey") == "POST /animals":
        dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")
        animal_id = new_ulid()

        item = {
                    "pk": f"ANIMAL#{animal_id}",
                    "sk": "PROFILE",
                    "entity": "animal",
                    "id": animal_id,
                    "number": event['number'],
                    "status": event['status'],
                    "sex": event['sex'],
                    "date_of_birth": event['date_of_birth']
                }

        dynamodb_table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    else:
        return {"statusCode": 404, "headers": {"content-type": "application/json"}, "message": "Route not found"}

