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
# Removal events take an active animal out of the herd, and each one sets the animal's status.
RemovalEventType = Literal["sold", "died", "processed"]
EventType = Literal[
    "castrated",
    "weaned",
    "note",
    "bred",
    "confirmed_pregnant",
    "confirmed_open",
    "calved",
    "lost",
    "sold",
    "died",
    "processed",
]
Category = Literal["Cow", "Bull", "Heifer", "Steer", "Heifer calf", "Bull calf", "Calf"]

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


BRED = frozenset({"bred"})
PREGNANT = frozenset({"pregnant"})
NOT_PREGNANT = frozenset({"unbred", "bred", "open"})
FEMALE_ONLY_ERROR = "Only female animals can have breeding events"

TRANSITIONS = {
    "bred": BreedingTransition(NOT_PREGNANT, "bred", "Pregnant animals can't be bred"),
    "confirmed_pregnant": BreedingTransition(BRED, "pregnant", "Only bred animals can be pregnancy checked"),
    "confirmed_open": BreedingTransition(BRED, "open", "Only bred animals can be pregnancy checked"),
    "calved": BreedingTransition(PREGNANT, "open", "Only pregnant animals can calve"),
    "lost": BreedingTransition(PREGNANT, "open", "Only pregnant animals can lose a pregnancy"),
}

# The status each removal event leaves the animal in; they all require it to be active.
REMOVAL_STATUS: dict[RemovalEventType, Status] = {"sold": "sold", "died": "deceased", "processed": "processed"}
NOT_ACTIVE_ERROR = "Only active animals can be removed from the herd"

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
    # Unknown (null) only for a calf born at a calving whose sex isn't known yet; POST /animals refuses it.
    sex: Sex | None
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

    # Unset sex isn't stored (None is omitted from the item), so reading it back needs a default.
    sex: Sex | None = None
    # The lambda looks up new_ulid at call time so tests can patch it.
    id: str = Field(default_factory=lambda: new_ulid())

    @computed_field
    @property
    def category(self) -> Category | None:
        """What the animal is called now; None when the age is unknown. Derived on read, never stored."""
        if self.date_of_birth is None:
            return None
        if is_calf(self.date_of_birth, today()):
            return {"male": "Bull calf", "female": "Heifer calf"}.get(self.sex, "Calf")
        if self.sex is None:
            return None
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


class CalfIn(BaseModel):
    """The calf born at a calving. It has no ear tag yet, so the server numbers it after its dam."""

    # Often not known until later; it can be set by editing the animal.
    sex: Sex | None = None


class BreedingEventIn(BaseModel):
    """Request body for POST /animals/<animal_id>/breeding-events."""

    type: BreedingEventType
    date: date
    notes: str | None = None
    # Only for a confirmed pregnancy.
    due_date: date | None = None
    # Only for a calving. Creates the calf animal along with the event.
    calf: CalfIn | None = None

    @model_validator(mode="after")
    def check_field_combinations(self) -> Self:
        if self.due_date is not None and self.type != "confirmed_pregnant":
            raise ValueError("due_date is only for a confirmed pregnancy")
        if self.calf is not None and self.type != "calved":
            raise ValueError("calf is only for a calving")
        return self

    @property
    def transition(self) -> BreedingTransition:
        return TRANSITIONS[self.type]


class RemovalEventIn(BaseModel):
    """Request body for POST /animals/<animal_id>/removal-events."""

    type: RemovalEventType
    date: date
    notes: str | None = None

    @property
    def to_status(self) -> Status:
        return REMOVAL_STATUS[self.type]


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
