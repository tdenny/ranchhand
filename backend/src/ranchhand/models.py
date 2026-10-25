from datetime import date

from pydantic import BaseModel


class AnimalIn(BaseModel):
    """Request body for POST /animals."""

    number: str
    status: str
    sex: str
    date_of_birth: date
