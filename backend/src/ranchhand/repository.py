"""Persistence for the single-table herd design: the only module that knows the key layout."""

from collections.abc import Iterable
from functools import cache

import boto3
from boto3.dynamodb.conditions import Key

from ranchhand.models import Animal, Event, Status

TABLE_NAME = "ranchhand-herd"
STATUS_INDEX = "status-index"


# The animal flag each milestone event sets (see Animal.castrated and Animal.bred).
EVENT_FLAGS = {"castrated": "castrated", "bred": "bred", "calved": "bred"}


def animal_key(animal_id: str) -> dict:
    return {"pk": f"ANIMAL#{animal_id}", "sk": "PROFILE"}


class HerdRepository:
    """Reads and writes animals and events, taking and returning models rather than raw items."""

    def __init__(self, table):
        self._table = table

    def _query_all(self, **query_kwargs) -> list[dict]:
        """Run a query, following pagination, and return every item."""
        items = []

        while True:
            page = self._table.query(**query_kwargs)
            items.extend(page["Items"])
            if "LastEvaluatedKey" not in page:
                return items
            query_kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def get_animal(self, animal_id: str) -> Animal | None:
        item = self._table.get_item(Key=animal_key(animal_id)).get("Item")
        return None if item is None else Animal.model_validate(item)

    def animal_exists(self, animal_id: str) -> bool:
        """Cheaper than get_animal, and doesn't validate the stored item."""
        item = self._table.get_item(Key=animal_key(animal_id), ProjectionExpression="pk").get("Item")
        return item is not None

    def put_animal(self, animal: Animal) -> None:
        """Store a new animal; raises ClientError if its id is already taken."""
        item = {
            **animal_key(animal.id),
            "entity": "animal",
            # Omit unset sire_id/dam_id: a NULL value is invalid for a GSI key attribute.
            # category is derived from the age on each read, so storing it would let it go stale.
            **animal.model_dump(mode="json", exclude_none=True, exclude={"category"}),
        }
        self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")

    def list_animals(self, statuses: Iterable[Status]) -> list[Animal]:
        """Return the animals with any of the given statuses, ordered by number."""
        items = []

        for status in dict.fromkeys(statuses):
            items.extend(
                self._query_all(IndexName=STATUS_INDEX, KeyConditionExpression=Key("status").eq(status))
            )

        # Each status comes back ordered by number (the index range key); merge them into one ordering.
        return sorted((Animal.model_validate(item) for item in items), key=lambda animal: animal.number)

    def put_event(self, event: Event) -> None:
        """Store a new event under its animal; raises ClientError if its id is already taken.

        A milestone event also sets its flag on the animal's profile, in the same transaction, so the
        two can't disagree. That raises ClientError too (TransactionCanceledException) if the animal
        doesn't exist.
        """
        item = {
            "pk": f"ANIMAL#{event.animal_id}",
            "sk": f"EVENT#{event.id}",
            "entity": "event",
            **event.model_dump(mode="json"),
        }
        flag = EVENT_FLAGS.get(event.type)

        if flag is None:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            return

        self._table.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": self._table.name,
                        "Item": item,
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
                {
                    "Update": {
                        "TableName": self._table.name,
                        "Key": animal_key(event.animal_id),
                        "UpdateExpression": "SET #flag = :true",
                        "ConditionExpression": "attribute_exists(pk)",
                        "ExpressionAttributeNames": {"#flag": flag},
                        "ExpressionAttributeValues": {":true": True},
                    }
                },
            ]
        )

    def list_events(self, animal_id: str) -> list[Event]:
        """Return an animal's events, newest first."""
        # Event sort keys are ULIDs, so key order is chronological.
        items = self._query_all(
            KeyConditionExpression=Key("pk").eq(f"ANIMAL#{animal_id}") & Key("sk").begins_with("EVENT#"),
            ScanIndexForward=False,
        )
        return [Event.model_validate(item) for item in items]


@cache
def get_repository() -> HerdRepository:
    """Return the shared repository, created on first use and reused by warm Lambda invocations.

    Created lazily because boto3 needs the AWS region at creation and moto only intercepts clients
    built while it is active; tests must call get_repository.cache_clear() when the table changes.
    """
    return HerdRepository(boto3.resource("dynamodb").Table(TABLE_NAME))
