from datetime import date
from typing import Literal, NamedTuple, Self

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from ranchhand.ulid import new_ulid

Status = Literal["active", "deceased", "processed", "sold", "external"]
Sex = Literal["female", "male"]
BreedingState = Literal["unbred", "bred", "pregnant", "open"]
# Log events record something that happened; castrated is also a milestone that changes the animal.
LogEventType = Literal["castrated", "weaned", "note"]
# Breeding events are the recurring workflow of a mature cow and move her through the BreedingStates.
# A pregnancy check is recorded as what it found, so each outcome is its own event type.
BreedingEventType = Literal["bred", "confirmed_pregnant", "confirmed_open", "calved", "lost"]
EventType = Literal["castrated", "weaned", "note", "bred", "confirmed_pregnant", "confirmed_open", "calved", "lost"]
Category = Literal["Cow", "Bull", "Heifer", "Steer", "Heifer calf", "Bull calf"]

GESTATION_DAYS = 283


class Milestone(NamedTuple):
    """What recording a milestone event means: the sex it applies to and the animal flag it sets."""

    sex: Sex
    flag: Literal["castrated"]
    error: str


# Event types not listed here (weaned, note) apply to either sex and leave the animal unchanged.
MILESTONES = {
    "castrated": Milestone("male", "castrated", "Only male animals can be castrated"),
}


class BreedingTransition(NamedTuple):
    """What a breeding event does to a female: the states she may be in (None: any), the one she ends in,
    as well as an error string for the case where she is not in one of the from_states"""

    from_states: frozenset[BreedingState] | None
    to_state: BreedingState
    error: str


BRED_OR_PREGNANT = frozenset({"bred", "pregnant"})
FEMALE_ONLY_ERROR = "Only female animals can have breeding events"

TRANSITIONS = {
    # None: a female can be bred again from any state, so there is no state to check (and no error to give).
    "bred": BreedingTransition(None, "bred", ""),
    "confirmed_pregnant": BreedingTransition(
        BRED_OR_PREGNANT, "pregnant", "Only bred or pregnant animals can be pregnancy checked"
    ),
    "confirmed_open": BreedingTransition(
        BRED_OR_PREGNANT, "open", "Only bred or pregnant animals can be pregnancy checked"
    ),
    "calved": BreedingTransition(BRED_OR_PREGNANT, "open", "Only bred or pregnant animals can calve"),
    "lost": BreedingTransition(frozenset({"pregnant"}), "open", "Only pregnant animals can lose a pregnancy"),
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
    # Female only: None means unset, which becomes "unbred" for a female and stays None for a male.
    breeding_state: BreedingState | None = None
    due_date: date | None = None

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
        if self.sex == "male" and self.breeding_state is not None:
            raise ValueError("Only female animals have a breeding state")
        if self.sex == "female" and self.breeding_state is None:
            self.breeding_state = "unbred"
        if self.due_date is not None and self.breeding_state != "pregnant":
            raise ValueError("due_date requires a pregnant animal")
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
        return "Heifer" if self.breeding_state == "unbred" else "Cow"


class AnimalList(BaseModel):
    """Response body for GET /animals."""

    animals: list[Animal]


class EventIn(BaseModel):
    """Request body for POST /animals/<animal_id>/events."""

    type: LogEventType
    date: date
    notes: str | None = None


class BreedingEventIn(BaseModel):
    """Request body for POST /animals/<animal_id>/breeding-events."""

    type: BreedingEventType
    date: date
    notes: str | None = None
    # Only for a confirmed pregnancy.
    due_date: date | None = None

    @model_validator(mode="after")
    def check_field_combinations(self) -> Self:
        if self.due_date is not None and self.type != "confirmed_pregnant":
            raise ValueError("due_date is only for a confirmed pregnancy")
        return self

    @property
    def transition(self) -> BreedingTransition:
        return TRANSITIONS[self.type]


class Event(BaseModel):
    """An animal event as stored and returned by the API."""

    id: str = Field(default_factory=lambda: new_ulid())
    animal_id: str
    type: EventType
    date: date
    notes: str | None = None
    due_date: date | None = None


class EventList(BaseModel):
    """Response body for GET /animals/<animal_id>/events."""

    events: list[Event]
