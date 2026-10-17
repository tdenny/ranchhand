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
    dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")
    animal_id = new_ulid()

    item = {
                "pk": f"ANIMAL#{animal_id}",
                "sk": "PROFILE",
                "entity": "animal",
                "id": animal_id,
                "number": "34",
                "status": "active",
                "sex": "male",
                "date_of_birth": "2017-03-01"
            }

    dynamodb_table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
