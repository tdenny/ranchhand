from datetime import date
from typing import Literal, NamedTuple, Self

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from ranchhand.ulid import new_ulid


Status = Literal["active", "deceased", "processed", "sold", "external"]
Sex = Literal["female", "male"]
# Milestones change an animal's state ("note" is a plain log entry that doesn't).
EventType = Literal["castrated", "bred", "calved", "weaned", "note"]
Category = Literal["Cow", "Bull", "Heifer", "Steer", "Heifer calf", "Bull calf"]


class Milestone(NamedTuple):
    """What recording a milestone event means: the sex it applies to and the animal flag it sets."""

    sex: Sex
    flag: Literal["castrated", "bred"]
    error: str


# Event types not listed here (weaned, note) apply to either sex and leave the animal unchanged.
MILESTONES = {
    "castrated": Milestone("male", "castrated", "Only male animals can be castrated"),
    "bred": Milestone("female", "bred", "Only female animals can be bred"),
    "calved": Milestone("female", "bred", "Only female animals can calve"),
}

CALF_YEARS = 2


def today() -> date:
    # A function so tests can patch it.
    return date.today()


def is_calf(date_of_birth: date, mature_on: date) -> bool:
    """Whether an animal born on date_of_birth is under CALF_YEARS old on the given date."""
    return (mature_on.year - CALF_YEARS, mature_on.month, mature_on.day) < (
        date_of_birth.year,
        date_of_birth.month,
        date_of_birth.day,
    )


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

    @computed_field
    @property
    def category(self) -> Category | None:
        """What the animal is called now; None when the age is unknown. Derived on read, never stored."""
        if self.date_of_birth is None:
            return None
        if is_calf(self.date_of_birth, today()):
            return "Bull calf" if self.sex == "male" else "Heifer calf"
        if self.sex == "male":
            return "Steer" if self.castrated else "Bull"
        return "Cow" if self.bred else "Heifer"


class AnimalList(BaseModel):
    """Response body for GET /animals."""

    animals: list[Animal]


class EventIn(BaseModel):
    """Request body for POST /animals/<animal_id>/events."""

    type: EventType
    date: date
    notes: str | None = None


class Event(EventIn):
    """An animal event as stored and returned by the API."""

    id: str = Field(default_factory=lambda: new_ulid())
    animal_id: str


class EventList(BaseModel):
    """Response body for GET /animals/<animal_id>/events."""

    events: list[Event]
