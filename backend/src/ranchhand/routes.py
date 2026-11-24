import hmac
import os
from datetime import date, timedelta
from typing import Annotated, get_args

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, CORSConfig, Response
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from aws_lambda_powertools.event_handler.middlewares import NextMiddleware
from aws_lambda_powertools.event_handler.openapi.exceptions import RequestValidationError
from aws_lambda_powertools.event_handler.openapi.params import Query

from ranchhand.models import (
    FEMALE_ONLY_ERROR,
    GESTATION_DAYS,
    MILESTONES,
    Animal,
    AnimalIn,
    AnimalList,
    BreedingEventIn,
    Event,
    EventIn,
    EventList,
    Status,
)
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


def invalid_parent_errors(animal_in: AnimalIn, animal_id: str | None = None) -> list[dict]:
    """Return a validation error for each of sire_id/dam_id that is not an existing animal of the right sex.

    animal_id is the animal being edited, if any, which can't be its own parent.
    """
    repo = get_repository()
    errors = []

    for field, sex in PARENT_SEX.items():
        parent_id = getattr(animal_in, field)
        if parent_id is None:
            continue

        parent = repo.get_animal(parent_id)

        if parent_id == animal_id:
            msg = "An animal cannot be its own parent"
        elif parent is None:
            msg = f"No animal with id {parent_id}"
        elif parent.sex != sex:
            msg = f"Animal {parent_id} is not {sex}"
        else:
            continue

        errors.append({"type": "value_error", "loc": ["body", field], "msg": msg})

    return errors


BREEDING_STATE_LOCKED = "Breeding events change this; it can't be edited"


def breeding_state_errors(animal_in: AnimalIn, current: Animal) -> list[dict]:
    """Return a validation error for each of breeding_state/due_date that an edit would change.

    Once an animal exists they only change by recording a breeding event (see TRANSITIONS). A male
    has no state, which counts as the same as unbred, so fixing a wrongly entered sex is still allowed.
    """
    errors = []

    if (animal_in.breeding_state or "unbred") != (current.breeding_state or "unbred"):
        errors.append({"type": "value_error", "loc": ["body", "breeding_state"], "msg": BREEDING_STATE_LOCKED})
    if animal_in.due_date != current.due_date:
        errors.append({"type": "value_error", "loc": ["body", "due_date"], "msg": BREEDING_STATE_LOCKED})

    return errors


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


@app.put("/animals/<animal_id>")
def update_animal(animal_id: str, animal_in: AnimalIn) -> Response[Animal]:
    """Replace every editable field of an existing animal; its id (and its events) stay as they were.

    The exception is its breeding state and due date, which only breeding events change."""
    repo = get_repository()
    current = repo.get_animal(animal_id)

    if current is None:
        raise NotFoundError(f"Animal {animal_id} not found")

    if errors := invalid_parent_errors(animal_in, animal_id) + breeding_state_errors(animal_in, current):
        raise RequestValidationError(errors)

    animal = Animal(id=animal_id, **animal_in.model_dump())
    repo.replace_animal(animal)

    return Response(status_code=200, content_type="application/json", body=animal)


@app.post("/animals/<animal_id>/events")
def create_animal_event(animal_id: str, event_in: EventIn) -> Response[Event]:
    """Write a new event for an existing animal to the herd table."""
    repo = get_repository()
    animal = repo.get_animal(animal_id)

    if animal is None:
        raise NotFoundError(f"Animal {animal_id} not found")

    milestone = MILESTONES.get(event_in.type)
    if milestone is not None and animal.sex != milestone.sex:
        raise RequestValidationError([{"type": "value_error", "loc": ["body", "type"], "msg": milestone.error}])

    event = Event(animal_id=animal_id, **event_in.model_dump())
    repo.put_event(event)

    return Response(
        status_code=201,
        content_type="application/json",
        headers={"location": f"/animals/{animal_id}/events/{event.id}"},
        body=event,
    )


@app.post("/animals/<animal_id>/breeding-events")
def create_animal_breeding_event(animal_id: str, event_in: BreedingEventIn) -> Response[Event]:
    """Write a breeding event for an existing female, and move her to the breeding state it leads to."""
    repo = get_repository()
    animal = repo.get_animal(animal_id)

    if animal is None:
        raise NotFoundError(f"Animal {animal_id} not found")

    transition = event_in.transition
    error = None
    if animal.sex != "female":
        error = FEMALE_ONLY_ERROR
    elif transition.from_states is not None and animal.breeding_state not in transition.from_states:
        error = transition.error
    if error:
        raise RequestValidationError([{"type": "value_error", "loc": ["body", "type"], "msg": error}])

    event = Event(animal_id=animal_id, **event_in.model_dump())
    if event.type == "confirmed_pregnant" and event.due_date is None:
        event.due_date = default_due_date(repo.list_events(animal_id), event.date)
    repo.put_breeding_event(event, transition.from_states, transition.to_state)

    return Response(
        status_code=201,
        content_type="application/json",
        headers={"location": f"/animals/{animal_id}/events/{event.id}"},
        body=event,
    )


def default_due_date(events: list[Event], checked_on: date) -> date | None:
    """The gestation period after the latest breeding on or before checked_on; None if none is recorded."""
    bred_dates = [e.date for e in events if e.type == "bred" and e.date <= checked_on]
    return max(bred_dates) + timedelta(days=GESTATION_DAYS) if bred_dates else None


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
