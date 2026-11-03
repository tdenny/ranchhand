from datetime import date

from pydantic import BaseModel, Field

from ranchhand.ulid import new_ulid


class AnimalIn(BaseModel):
    """Request body for POST /animals."""

    number: str
    status: str
    sex: str
    date_of_birth: date


class Animal(AnimalIn):
    """An animal as stored and returned by the API."""

    # The lambda looks up new_ulid at call time so tests can patch it.
    id: str = Field(default_factory=lambda: new_ulid())
