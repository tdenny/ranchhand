=========
ranchhand
=========

Creating the Terraform state bucket
===================================

Terraform stores its state in an S3 bucket. Terraform cannot create the bucket
it keeps its own state in, so create it once by hand before running
``terraform init``.

Bucket names are global across all AWS accounts, so choose a unique name such
as ``ranchhand-tfstate-<account-id>``. The region should match ``aws_region``
in ``infra/variables.tf`` (``us-east-2``).

.. code-block:: bash

   BUCKET=<name>
   REGION=us-east-2

   # Create the bucket
   aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
     --create-bucket-configuration LocationConstraint="$REGION"

   # Keep old versions of the state file so it can be recovered
   aws s3api put-bucket-versioning --bucket "$BUCKET" \
     --versioning-configuration Status=Enabled

   # Encrypt objects at rest
   aws s3api put-bucket-encryption --bucket "$BUCKET" \
     --server-side-encryption-configuration \
     '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

   # Block all public access
   aws s3api put-public-access-block --bucket "$BUCKET" \
     --public-access-block-configuration \
     BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

The bucket name is kept out of the repository. Copy
``infra/backend.hcl.example`` to ``infra/backend.hcl`` (git-ignored), put the
bucket name in it, and initialise Terraform with:

.. code-block:: bash

   cd infra
   terraform init -backend-config=backend.hcl
