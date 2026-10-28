import boto3
from boto3.dynamodb.conditions import Attr
from os import urandom
import time

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.exceptions import BadRequestError
from aws_lambda_powertools.event_handler.openapi.exceptions import RequestValidationError

from ranchhand.models import AnimalIn

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def new_ulid(now_ms=None):
    """48-bit millisecond timestamp + 80 random bits, as 26 sortable characters."""
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    n = (ts << 80) | int.from_bytes(urandom(10), "big")
    return "".join(_ALPHABET[(n >> (5 * i)) & 31] for i in reversed(range(26)))


app = APIGatewayHttpResolver(enable_validation=True)


@app.exception_handler(RequestValidationError)
def invalid_request(exc: RequestValidationError):
    return Response(
        status_code=400,
        content_type="application/json",
        body={
            "statusCode": 400,
            "message": "Invalid request",
            "errors": [{key: err[key] for key in ("type", "loc", "msg")} for err in exc.errors()],
        },
    )


def require_json_object(app, next_middleware):
    """Reject non-object JSON bodies; validation would otherwise take the first element of an array."""
    try:
        body = app.current_event.json_body
    except ValueError:  # let validation report malformed JSON
        body = None
    if body is not None and not isinstance(body, dict):
        raise BadRequestError("Request body must be a JSON object")
    return next_middleware(app)


@app.post("/animals", middlewares=[require_json_object])
def create_animal(animal_in: AnimalIn) -> Response[dict]:
    """Write a new animal profile to the herd table."""
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


@app.get("/animals")
def list_animals() -> Response[dict]:
    """Return every animal profile in the herd table."""
    dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")
    scan_kwargs = {"FilterExpression": Attr("entity").eq("animal")}
    items = []

    while True:
        page = dynamodb_table.scan(**scan_kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        scan_kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    animals = [{k: v for k, v in item.items() if k not in ("pk", "sk", "entity")} for item in items]

    return Response(
        status_code=200,
        content_type="application/json",
        body={"animals": animals},
    )


def handler(event, context):
    return app.resolve(event, context)
