from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ranchhand.ulid import new_ulid


Status = Literal["active", "deceased", "processed", "sold"]


class AnimalIn(BaseModel):
    """Request body for POST /animals."""

    number: str
    status: Status
    sex: str
    date_of_birth: date
    sire_id: str | None = None
    dam_id: str | None = None

    @field_validator("sire_id", "dam_id")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        # These are GSI keys (see infra/dynamodb.tf); DynamoDB rejects empty strings for them.
        return value.strip() or None if value is not None else None


class Animal(AnimalIn):
    """An animal as stored and returned by the API."""

    # The lambda looks up new_ulid at call time so tests can patch it.
    id: str = Field(default_factory=lambda: new_ulid())


class AnimalList(BaseModel):
    """Response body for GET /animals."""

    animals: list[Animal]


class EventIn(BaseModel):
    """Request body for POST /animals/<animal_id>/events."""

    type: str
    date: date
    notes: str | None = None


class Event(EventIn):
    """An animal event as stored and returned by the API."""

    id: str = Field(default_factory=lambda: new_ulid())
    animal_id: str


class EventList(BaseModel):
    """Response body for GET /animals/<animal_id>/events."""

    events: list[Event]
