"""Persistence for the single-table herd design: the only module that knows the key layout."""

from collections.abc import Iterable
from functools import cache

import boto3
from boto3.dynamodb.conditions import Key

from ranchhand.models import MILESTONES, Animal, BreedingState, Event, Status

TABLE_NAME = "ranchhand-herd"
STATUS_INDEX = "status-index"


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

    @staticmethod
    def _animal_item(animal: Animal) -> dict:
        return {
            **animal_key(animal.id),
            "entity": "animal",
            # Omit unset sire_id/dam_id: a NULL value is invalid for a GSI key attribute.
            # category is derived from the age on each read, so storing it would let it go stale.
            **animal.model_dump(mode="json", exclude_none=True, exclude={"category"}),
        }

    def put_animal(self, animal: Animal) -> None:
        """Store a new animal; raises ClientError if its id is already taken."""
        self._table.put_item(Item=self._animal_item(animal), ConditionExpression="attribute_not_exists(pk)")

    def replace_animal(self, animal: Animal) -> None:
        """Overwrite an existing animal's profile; raises ClientError if there is no such animal.

        The whole item is replaced, so a cleared sire_id/dam_id (omitted by _animal_item) is removed.
        Events are separate items and are untouched.
        """
        self._table.put_item(Item=self._animal_item(animal), ConditionExpression="attribute_exists(pk)")

    def list_animals(self, statuses: Iterable[Status]) -> list[Animal]:
        """Return the animals with any of the given statuses, ordered by number."""
        items = []

        for status in dict.fromkeys(statuses):
            items.extend(self._query_all(IndexName=STATUS_INDEX, KeyConditionExpression=Key("status").eq(status)))

        # Each status comes back ordered by number (the index range key); merge them into one ordering.
        return sorted((Animal.model_validate(item) for item in items), key=lambda animal: animal.number)

    def put_event(self, event: Event) -> None:
        """Store a new event under its animal; raises ClientError if its id is already taken.

        A milestone event also sets its flag on the animal's profile, in the same transaction, so the
        two can't disagree. That raises ClientError too (TransactionCanceledException) if the animal
        doesn't exist.
        """
        item = self._event_item(event)
        milestone = MILESTONES.get(event.type)

        if milestone is None:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            return

        self._write_event_and_profile(
            item,
            {
                "Key": animal_key(event.animal_id),
                "UpdateExpression": "SET #flag = :true",
                "ConditionExpression": "attribute_exists(pk)",
                "ExpressionAttributeNames": {"#flag": milestone.flag},
                "ExpressionAttributeValues": {":true": True},
            },
        )

    def put_breeding_event(
        self,
        event: Event,
        from_states: frozenset[BreedingState] | None,
        to_state: BreedingState,
        calf: Animal | None = None,
    ) -> None:
        """Store a breeding event and move the animal to to_state, clearing its due date unless the event has one.

        A calf, if given, is stored as a new animal in the same transaction. All of it happens in one
        transaction, which also requires the animal to be in one of from_states (None:
        any) when it commits, so a change since the caller read the animal can't slip past. Raises
        ClientError (TransactionCanceledException) if it isn't, if it doesn't exist, or if the event or calf
        id is taken.
        """
        values = {":to": to_state}
        update = "SET breeding_state = :to"
        if event.due_date is not None:
            update += ", due_date = :due"
            values[":due"] = event.due_date.isoformat()
        else:
            update += " REMOVE due_date"

        condition = "attribute_exists(pk)"
        if from_states is not None:
            states = sorted(from_states)
            values.update({f":from{i}": state for i, state in enumerate(states)})
            condition += " AND breeding_state IN (" + ", ".join(f":from{i}" for i in range(len(states))) + ")"

        self._write_event_and_profile(
            self._event_item(event),
            {
                "Key": animal_key(event.animal_id),
                "UpdateExpression": update,
                "ConditionExpression": condition,
                "ExpressionAttributeValues": values,
            },
            extra_puts=[self._animal_item(calf)] if calf is not None else [],
        )

    def put_removal_event(self, event: Event, to_status: Status) -> None:
        """Store a removal event and set the animal's status to to_status.

        One transaction, which also requires the animal to be active when it commits. Raises ClientError
        (TransactionCanceledException) if it isn't, if it doesn't exist, or if the event id is taken.
        """
        self._write_event_and_profile(
            self._event_item(event),
            {
                "Key": animal_key(event.animal_id),
                "UpdateExpression": "SET #status = :to",
                "ConditionExpression": "attribute_exists(pk) AND #status = :active",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {":to": to_status, ":active": "active"},
            },
        )

    @staticmethod
    def _event_item(event: Event) -> dict:
        return {
            "pk": f"ANIMAL#{event.animal_id}",
            "sk": f"EVENT#{event.id}",
            "entity": "event",
            **event.model_dump(mode="json"),
        }

    def _write_event_and_profile(self, event_item: dict, profile_update: dict, extra_puts: list[dict] = ()) -> None:
        """Write the event and the profile update, and any other new items, as one transaction."""
        self._table.meta.client.transact_write_items(
            TransactItems=[
                *(
                    {
                        "Put": {
                            "TableName": self._table.name,
                            "Item": item,
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    }
                    for item in (event_item, *extra_puts)
                ),
                {"Update": {"TableName": self._table.name, **profile_update}},
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
