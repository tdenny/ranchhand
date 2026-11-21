from datetime import date

import pytest

from ranchhand import models
from ranchhand.models import Animal, is_calf

TODAY = date(2026, 11, 21)


def animal(**fields):
    return Animal(**{"number": "1", "status": "active", "sex": "female", "date_of_birth": "2020-04-01", **fields})


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(models, "today", lambda: TODAY)


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"sex": "female"}, "Heifer"),
        ({"sex": "female", "bred": True}, "Cow"),
        ({"sex": "male"}, "Bull"),
        ({"sex": "male", "castrated": True}, "Steer"),
        ({"sex": "female", "date_of_birth": "2025-01-01"}, "Heifer calf"),
        ({"sex": "male", "date_of_birth": "2025-01-01"}, "Bull calf"),
        # Calves stay calves whatever their flags say.
        ({"sex": "female", "bred": True, "date_of_birth": "2025-01-01"}, "Heifer calf"),
        ({"sex": "male", "castrated": True, "date_of_birth": "2025-01-01"}, "Bull calf"),
    ],
)
def test_category(fields, expected):
    assert animal(**fields).category == expected


def test_category_is_unknown_without_a_date_of_birth():
    assert animal(status="external", date_of_birth=None).category is None


def test_category_changes_as_the_animal_ages(monkeypatch):
    calf = animal(sex="male", date_of_birth="2024-12-01")
    assert calf.category == "Bull calf"

    monkeypatch.setattr(models, "today", lambda: date(2026, 12, 1))

    assert calf.category == "Bull"


@pytest.mark.parametrize(
    "date_of_birth, on, expected",
    [
        (date(2024, 11, 22), TODAY, True),  # Turns 2 tomorrow.
        (date(2024, 11, 21), TODAY, False),  # Turns 2 today.
        (date(2024, 11, 20), TODAY, False),
        (date(2026, 11, 21), TODAY, True),  # Born today.
        (date(2024, 2, 29), date(2026, 2, 28), True),  # Leap-day birthday: adult on Mar 1 in other years.
        (date(2024, 2, 29), date(2026, 3, 1), False),
    ],
)
def test_is_calf(date_of_birth, on, expected):
    assert is_calf(date_of_birth, on) is expected
