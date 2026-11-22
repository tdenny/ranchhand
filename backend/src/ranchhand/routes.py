import hmac
import os
from typing import Annotated, get_args

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, CORSConfig, Response
from aws_lambda_powertools.event_handler.middlewares import NextMiddleware
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from aws_lambda_powertools.event_handler.openapi.exceptions import RequestValidationError
from aws_lambda_powertools.event_handler.openapi.params import Query

from ranchhand.models import Animal, AnimalIn, AnimalList, Event, EventIn, EventList, Status
from ranchhand.repository import get_repository

# A little awkward for now, but browsers send a credential-less preflight
# before the Authorization header; allow only the configured frontend origin.
# With CORS_ALLOW_ORIGIN unset, no origin is allowed.
cors_config = CORSConfig(allow_origin=os.environ.get("CORS_ALLOW_ORIGIN", ""))

app = APIGatewayHttpResolver(enable_validation=True, cors=cors_config)


def unauthorized_response() -> Response | None:
    """Return a 401 unless the request carries the shared bearer token in API_TOKEN."""
    expected = os.environ.get("API_TOKEN", "")
    header = app.current_event.headers.get("authorization", "")
    scheme, _, supplied = header.partition(" ")

    if expected and scheme.lower() == "bearer" and hmac.compare_digest(supplied.encode(), expected.encode()):
        return None

    return Response(
        status_code=401,
        content_type="application/json",
        headers={"WWW-Authenticate": "Bearer"},
        body={"statusCode": 401, "message": "Unauthorized"},
    )


def require_token(app: APIGatewayHttpResolver, next_middleware: NextMiddleware) -> Response:
    # CORS preflights are sent without credentials and return no data.
    if app.current_event.http_method == "OPTIONS":
        return next_middleware(app)

    return unauthorized_response() or next_middleware(app)


app.use(middlewares=[require_token])


@app.exception_handler(RequestValidationError)
def invalid_request(exc: RequestValidationError):
    # Validation runs before middleware; don't describe the schema to unauthenticated callers.
    if (rejection := unauthorized_response()) is not None:
        return rejection

    return Response(
        status_code=400,
        content_type="application/json",
        body={
            "statusCode": 400,
            "message": "Invalid request",
            "errors": [{key: err[key] for key in ("type", "loc", "msg")} for err in exc.errors()],
        },
    )


# The sex each parent field must refer to.
PARENT_SEX = {"sire_id": "male", "dam_id": "female"}


def invalid_parent_errors(animal_in: AnimalIn) -> list[dict]:
    """Return a validation error for each of sire_id/dam_id that is not an existing animal of the right sex."""
    repo = get_repository()
    errors = []

    for field, sex in PARENT_SEX.items():
        parent_id = getattr(animal_in, field)
        if parent_id is None:
            continue

        parent = repo.get_animal(parent_id)

        if parent is None:
            msg = f"No animal with id {parent_id}"
        elif parent.sex != sex:
            msg = f"Animal {parent_id} is not {sex}"
        else:
            continue

        errors.append({"type": "value_error", "loc": ["body", field], "msg": msg})

    return errors


# The sex each milestone event applies to, and the error when it's recorded for the other sex.
# Event types not listed here (weaned, note) apply to either sex.
EVENT_SEX_RULES = {
    "castrated": ("male", "Only male animals can be castrated"),
    "bred": ("female", "Only female animals can be bred"),
    "calved": ("female", "Only female animals can calve"),
}


@app.post("/animals")
def create_animal(animal_in: AnimalIn) -> Response[Animal]:
    """Write a new animal profile to the herd table."""
    # The new animal's id is generated here, so it can never be its own parent.
    if errors := invalid_parent_errors(animal_in):
        # Handled by invalid_request(), so these look like any other validation failure.
        raise RequestValidationError(errors)

    animal = Animal(**animal_in.model_dump())
    get_repository().put_animal(animal)

    return Response(
        status_code=201,
        content_type="application/json",
        headers={"location": f"/animals/{animal.id}"},
        body=animal,
    )


@app.get("/animals")
def list_animals(status: Annotated[list[Status] | None, Query()] = None) -> Response[AnimalList]:
    """Return animal profiles, optionally limited to the given statuses (repeat ?status=).

    Without a status filter, every animal except external ones is returned.
    """
    statuses = status or [s for s in get_args(Status) if s != "external"]

    return Response(
        status_code=200,
        content_type="application/json",
        body=AnimalList(animals=get_repository().list_animals(statuses)),
    )


@app.get("/animals/<animal_id>")
def get_animal(animal_id: str) -> Response[Animal]:
    """Return a single animal profile."""
    animal = get_repository().get_animal(animal_id)

    if animal is None:
        raise NotFoundError(f"Animal {animal_id} not found")

    return Response(status_code=200, content_type="application/json", body=animal)


@app.post("/animals/<animal_id>/events")
def create_animal_event(animal_id: str, event_in: EventIn) -> Response[Event]:
    """Write a new event for an existing animal to the herd table."""
    repo = get_repository()
    animal = repo.get_animal(animal_id)

    if animal is None:
        raise NotFoundError(f"Animal {animal_id} not found")

    rule = EVENT_SEX_RULES.get(event_in.type)
    if rule is not None and animal.sex != rule[0]:
        raise RequestValidationError([{"type": "value_error", "loc": ["body", "type"], "msg": rule[1]}])

    event = Event(animal_id=animal_id, **event_in.model_dump())
    repo.put_event(event)

    return Response(
        status_code=201,
        content_type="application/json",
        headers={"location": f"/animals/{animal_id}/events/{event.id}"},
        body=event,
    )


@app.get("/animals/<animal_id>/events")
def list_animal_events(animal_id: str) -> Response[EventList]:
    """Return an animal's events, newest first."""
    repo = get_repository()

    if not repo.animal_exists(animal_id):
        raise NotFoundError(f"Animal {animal_id} not found")

    return Response(
        status_code=200,
        content_type="application/json",
        body=EventList(events=repo.list_events(animal_id)),
    )
