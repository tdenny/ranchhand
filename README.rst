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
