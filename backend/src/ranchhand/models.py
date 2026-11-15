from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from ranchhand.ulid import new_ulid


Status = Literal["active", "deceased", "processed", "sold", "external"]
Sex = Literal["female", "male"]


class AnimalIn(BaseModel):
    """Request body for POST /animals."""

    number: str
    status: Status
    sex: Sex
    # validate_default so the validator below also runs when the field is omitted.
    date_of_birth: date | None = Field(default=None, validate_default=True)
    sire_id: str | None = None
    dam_id: str | None = None

    @field_validator("sire_id", "dam_id")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        # These are GSI keys (see infra/dynamodb.tf); DynamoDB rejects empty strings for them.
        return value.strip() or None if value is not None else None

    @field_validator("date_of_birth")
    @classmethod
    def require_date_of_birth_unless_external(cls, value: date | None, info: ValidationInfo) -> date | None:
        # External animals often have no known birth date.
        # info.data only holds fields validated before this one, so this relies on `status` being
        # declared above `date_of_birth`; reordering them silently disables the check.
        # If status itself failed validation it is absent from info.data; that error is already reported.
        if value is None and "status" in info.data and info.data["status"] != "external":
            raise ValueError("Field required for animals that are not external")
        return value


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
