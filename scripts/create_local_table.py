"""Create the ranchhand-herd table (mirrors infra/dynamodb.tf) in DynamoDB Local."""

import boto3

S = "S"
ATTRS = ["pk", "sk", "number", "status", "date_of_birth", "sire_id", "dam_id"]


def gsi(name, hash_key, range_key):
    return {
        "IndexName": name,
        "KeySchema": [
            {"AttributeName": hash_key, "KeyType": "HASH"},
            {"AttributeName": range_key, "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }


boto3.client("dynamodb").create_table(
    TableName="ranchhand-herd",
    BillingMode="PAY_PER_REQUEST",
    AttributeDefinitions=[{"AttributeName": a, "AttributeType": S} for a in ATTRS],
    KeySchema=[
        {"AttributeName": "pk", "KeyType": "HASH"},
        {"AttributeName": "sk", "KeyType": "RANGE"},
    ],
    GlobalSecondaryIndexes=[
        gsi("number-index", "number", "pk"),
        gsi("status-index", "status", "date_of_birth"),
        gsi("sire-index", "sire_id", "date_of_birth"),
        gsi("dam-index", "dam_id", "date_of_birth"),
    ],
)
print("created ranchhand-herd")
