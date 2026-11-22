import boto3
import pytest
from helpers import TODAY, TOKEN, ULID
from moto import mock_aws

from ranchhand import models
from ranchhand.repository import get_repository


@pytest.fixture(autouse=True)
def api_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(models, "today", lambda: TODAY)


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(models, "new_ulid", lambda: ULID)
    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="ranchhand-herd",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": a, "AttributeType": "S"}
                for a in ("pk", "sk", "number", "status", "date_of_birth", "sire_id", "dam_id")
            ],
            # Mirrors infra/dynamodb.tf.
            GlobalSecondaryIndexes=[
                {
                    "IndexName": name,
                    "KeySchema": [
                        {"AttributeName": hash_key, "KeyType": "HASH"},
                        {"AttributeName": range_key, "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
                for name, hash_key, range_key in (
                    ("number-index", "number", "pk"),
                    ("status-index", "status", "number"),
                    ("sire-index", "sire_id", "date_of_birth"),
                    ("dam-index", "dam_id", "date_of_birth"),
                )
            ],
        )
        # The repository is cached for warm Lambdas; make sure it binds to this test's table.
        get_repository.cache_clear()
        try:
            yield table
        finally:
            get_repository.cache_clear()
