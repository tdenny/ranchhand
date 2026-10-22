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

GitHub Actions OIDC roles
=========================

If using GitHub Actions for CI, follow these instructions to set up auth between
GitHub and AWS. Otherwise, delete or comment out ``infra/github-oidc.tf``.

GitHub Actions runs ``terraform plan`` and ``terraform apply`` by assuming IAM
roles through OpenID Connect, so no long-lived AWS access keys are stored in
GitHub. The roles are defined in ``infra/github-oidc.tf``.

``gha-ranchhand-plan``
   Read-only (AWS ``ReadOnlyAccess`` plus access to the state file and its lock
   object). Pull requests and the ``main`` branch may assume it.

``gha-ranchhand-apply``
   Read access plus write access to ``ranchhand-*`` Lambda functions, DynamoDB
   tables, log groups and IAM roles, and to API Gateway and Cognito. Only the
   ``main`` branch may assume it.

The roles are named outside the ``ranchhand-*`` pattern so the apply role cannot
change its own permissions. Create or change them with admin credentials, not
through the pipeline.

One-time setup
--------------

1. Set the following in ``infra/terraform.tfvars`` (git-ignored). The role
   policies need the state bucket name, and the role trust policies only allow
   workflows from the GitHub repository named in ``github_repository``:

   .. code-block:: hcl

      tf_state_bucket   = "<your-state-bucket-name>"
      github_repository = "<owner>/<repository>"

2. Create the roles, targeting only the CI resources so the application
   resources are not deployed yet:

   .. code-block:: bash

      cd infra
      terraform apply \
        -target=aws_iam_openid_connect_provider.github \
        -target=aws_iam_role.gha_plan \
        -target=aws_iam_role.gha_apply \
        -target=aws_iam_role_policy.gha_plan_state \
        -target=aws_iam_role_policy.gha_apply \
        -target=aws_iam_role_policy_attachment.gha_plan_readonly \
        -target=aws_iam_role_policy_attachment.gha_apply_readonly

3. Read the role ARNs for the workflow:

   .. code-block:: bash

      terraform output gha_plan_role_arn
      terraform output gha_apply_role_arn

In the workflow
---------------

The job needs ``permissions: id-token: write`` and must pass the role ARN to
``aws-actions/configure-aws-credentials``. Terraform receives the state bucket
name through ``-backend-config="bucket=..."`` and the
``TF_VAR_tf_state_bucket`` environment variable, and the repository through
``TF_VAR_github_repository``. Take the bucket name from a GitHub repository
variable or secret.
