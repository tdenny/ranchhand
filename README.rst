=========
ranchhand
=========

Ranchhand is a simple tool for ranchers to keep track of their animals. It
keeps a record for each animal, such as its tag number, sex, date of birth and
medical history, so you always know what is in your herd and how healthy it is.

Architecture
============

The API runs as a Python AWS Lambda function behind an API Gateway, with animal
records stored in DynamoDB. Infrastructure is managed with Terraform in
``infra/``. See `docs/setup.rst <docs/setup.rst>`_ for the setup
needed to deploy it.

Local development
=================

Set up the Python environment and run the tests (they use ``moto``, so nothing
else needs to be running)::

    python3 -m venv .venv
    source .venv/bin/activate
    cd backend
    pip install -r requirements-dev.txt
    pytest
    cd ..

To invoke the function locally, start DynamoDB Local in Docker/Podman and
create the ``ranchhand-herd`` table::

    scripts/local-dynamodb.sh

Then build the local package.
Re-run this after changing anything under ``backend/src`` or
``backend/requirements.txt``::

    rm -rf .aws-sam/local-package
    pip install -r backend/requirements.txt \
                --target .aws-sam/local-package \
                --platform manylinux2014_x86_64 \
                --implementation cp \
                --python-version 3.13 \
                --only-binary=:all:
    cp -r backend/src/. .aws-sam/local-package

On SELinux hosts, label the package so the container can read it (otherwise the
invoke fails with ``No module named 'ranchhand'``)::

    chcon -R -t container_file_t .aws-sam/local-package

Finally, invoke the function with one of the sample events in ``events/``::

    $ sam local invoke ApiFunction -e events/create-animal.json

    No current session found, using default AWS::AccountId
    Invoking ranchhand.handler.handler (python3.13)
    Requested to skip pulling images ...

    Mounting ~/Projects/ranchhand/.aws-sam/local-package as /var/task:ro,delegated, inside runtime container
    SAM_CONTAINER_ID: 2c10d4139542ab89580e450313b290ada9c6244d15a91bc07d8df312ad962acc
    START RequestId: d921ad62-0aed-4e7a-898f-22cf821f55de Version: $LATEST
    START RequestId: d921ad62-0aed-4e7a-898f-22cf821f55de Version: $LATEST
    END RequestId: d921ad62-0aed-4e7a-898f-22cf821f55de
    REPORT RequestId: d921ad62-0aed-4e7a-898f-22cf821f55de	Init Duration: 0.01 ms	Duration: 249.00 ms	Billed Duration: 249 ms	Memory Size: 256 MB	Max Memory Used: 256 MB
    {"statusCode": 201, "headers": {"content-type": "application/json", "location": "/animals/01M5T0CPNF8QRAMRRY0ZV9YJD2"}, "body": "{\"id\": \"01M5T0CPNF8QRAMRRY0ZV9YJD2\", \"number\": \"99\", \"status\": \"active\", \"sex\": \"female\", \"date_of_birth\": \"2024-03-01\"}"}

Stop DynamoDB Local when finished::

    podman rm -f ranchhand-ddb
