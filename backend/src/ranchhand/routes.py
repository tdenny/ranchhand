import boto3
from boto3.dynamodb.conditions import Attr

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from aws_lambda_powertools.event_handler.openapi.exceptions import RequestValidationError

from ranchhand.models import Animal, AnimalIn, AnimalList

app = APIGatewayHttpResolver(enable_validation=True)


def get_ddb_table():
    """Return the herd DynamoDB table resource."""
    return boto3.resource("dynamodb").Table("ranchhand-herd")


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


@app.post("/animals")
def create_animal(animal_in: AnimalIn) -> Response[Animal]:
    """Write a new animal profile to the herd table."""
    dynamodb_table = get_ddb_table()
    animal = Animal(**animal_in.model_dump())

    db_record = {
        "pk": f"ANIMAL#{animal.id}",
        "sk": "PROFILE",
        "entity": "animal",
        **animal.model_dump(mode="json"),
    }

    dynamodb_table.put_item(Item=db_record, ConditionExpression="attribute_not_exists(pk)")

    return Response(
        status_code=201,
        content_type="application/json",
        headers={"location": f"/animals/{animal.id}"},
        body=animal,
    )


@app.get("/animals")
def list_animals() -> Response[AnimalList]:
    """Return every animal profile in the herd table."""
    dynamodb_table = get_ddb_table()
    scan_kwargs = {"FilterExpression": Attr("entity").eq("animal")}
    items = []

    while True:
        page = dynamodb_table.scan(**scan_kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        scan_kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    return Response(
        status_code=200,
        content_type="application/json",
        body=AnimalList(animals=items),
    )


@app.get("/animals/<animal_id>")
def get_animal(animal_id: str) -> Response[Animal]:
    """Return a single animal profile."""
    dynamodb_table = get_ddb_table()
    item = dynamodb_table.get_item(Key={"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE"}).get("Item")

    if item is None:
        raise NotFoundError(f"Animal {animal_id} not found")

    return Response(
        status_code=200,
        content_type="application/json",
        body=Animal.model_validate(item),
    )
