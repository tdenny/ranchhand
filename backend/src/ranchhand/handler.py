import boto3
from os import urandom
import time

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.exceptions import BadRequestError
from pydantic import ValidationError

from ranchhand.models import AnimalIn

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def new_ulid(now_ms=None):
    """48-bit millisecond timestamp + 80 random bits, as 26 sortable characters."""
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    n = (ts << 80) | int.from_bytes(urandom(10), "big")
    return "".join(_ALPHABET[(n >> (5 * i)) & 31] for i in reversed(range(26)))


app = APIGatewayHttpResolver()


@app.exception_handler(ValidationError)
def invalid_animal(exc: ValidationError):
    return Response(
        status_code=400,
        content_type="application/json",
        body={
            "statusCode": 400,
            "message": "Invalid animal",
            "errors": exc.errors(include_url=False, include_context=False, include_input=False),
        },
    )


@app.post("/animals")
def create_animal():
    """Write a new animal profile to the herd table."""
    try:
        body = app.current_event.json_body
    except ValueError:  # bad JSON, bad base64, or non-UTF-8 bytes
        raise BadRequestError("Request body must be valid JSON")
    if not isinstance(body, dict):
        raise BadRequestError("Request body must be a JSON object")

    animal_in = AnimalIn.model_validate(body)  # ValidationError is handled by invalid_animal

    dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")
    animal = {"id": new_ulid(), **animal_in.model_dump(mode="json")}

    db_record = {
        "pk": f"ANIMAL#{animal['id']}",
        "sk": "PROFILE",
        "entity": "animal",
        **animal,
    }

    dynamodb_table.put_item(Item=db_record, ConditionExpression="attribute_not_exists(pk)")

    return Response(
        status_code=201,
        content_type="application/json",
        headers={"location": f"/animals/{animal['id']}"},
        body=animal,
    )


def handler(event, context):
    return app.resolve(event, context)
