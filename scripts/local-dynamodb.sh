#!/usr/bin/env bash
# Start DynamoDB Local in podman and create the ranchhand-herd table.
set -euo pipefail
cd "$(dirname "$0")/.."

podman rm -f ranchhand-ddb >/dev/null 2>&1 || true
podman run -d --name ranchhand-ddb -p 8000:8000 docker.io/amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -inMemory >/dev/null

export AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000
export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_DEFAULT_REGION=us-east-1
sleep 2
python3 scripts/create_local_table.py
