from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from ranchhand.ulid import new_ulid


Status = Literal["active", "deceased", "processed", "sold", "external"]
Sex = Literal["female", "male"]


class AnimalIn(BaseModel):
    """Request body for POST /animals."""

    number: str
    status: Status
    sex: Sex
    date_of_birth: date | None = None
    sire_id: str | None = None
    dam_id: str | None = None
    castrated: bool = False
    bred: bool = False

    @field_validator("sire_id", "dam_id")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        # These are GSI keys (see infra/dynamodb.tf); DynamoDB rejects empty strings for them.
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def check_field_combinations(self) -> Self:
        if self.date_of_birth is None and self.status != "external":
            raise ValueError("date_of_birth is required for animals that are not external")
        if self.castrated and self.sex == "female":
            raise ValueError("Only male animals can be castrated")
        if self.bred and self.sex == "male":
            raise ValueError("Only female animals can be bred")
        return self


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
