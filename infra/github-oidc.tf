# Roles that GitHub Actions assumes via OIDC to run `terraform plan` and `terraform apply`.
#
#   gha-ranchhand-plan  - read-only; assumable from pull requests and main
#   gha-ranchhand-apply - can change ranchhand-* resources; assumable only from main
#
# These roles are deliberately named outside the ranchhand-* pattern the apply role may
# manage, so a pipeline run cannot edit its own permissions. Change this file with admin
# credentials, not through CI.

data "aws_caller_identity" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  state_key     = "ranchhand/terraform.tfstate"
  state_bucket  = "arn:aws:s3:::${var.tf_state_bucket}"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "gha_plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:pull_request",
        "repo:${var.github_repository}:ref:refs/heads/main",
      ]
    }
  }
}

data "aws_iam_policy_document" "gha_apply_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

# --- plan role ---

resource "aws_iam_role" "gha_plan" {
  name                 = "gha-ranchhand-plan"
  assume_role_policy   = data.aws_iam_policy_document.gha_plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "gha_plan_readonly" {
  role       = aws_iam_role.gha_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "gha_plan_state" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket]
  }

  statement {
    actions   = ["s3:GetObject"]
    resources = ["${local.state_bucket}/${local.state_key}"]
  }

  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.state_bucket}/${local.state_key}.tflock"]
  }
}

resource "aws_iam_role_policy" "gha_plan_state" {
  name   = "terraform-state"
  role   = aws_iam_role.gha_plan.id
  policy = data.aws_iam_policy_document.gha_plan_state.json
}

# --- apply role ---

resource "aws_iam_role" "gha_apply" {
  name                 = "gha-ranchhand-apply"
  assume_role_policy   = data.aws_iam_policy_document.gha_apply_trust.json
  max_session_duration = 3600
}

# Read access for refresh/plan; the policy below adds write access for ranchhand-* resources.
resource "aws_iam_role_policy_attachment" "gha_apply_readonly" {
  role       = aws_iam_role.gha_apply.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "gha_apply" {
  statement {
    sid       = "TerraformStateBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket]
  }

  statement {
    sid     = "TerraformStateObjects"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${local.state_bucket}/${local.state_key}",
      "${local.state_bucket}/${local.state_key}.tflock",
    ]
  }

  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = ["arn:aws:lambda:${var.aws_region}:${local.account_id}:function:ranchhand-*"]
  }

  statement {
    sid     = "DynamoDB"
    actions = ["dynamodb:*"]
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/ranchhand-*",
      "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/ranchhand-*/index/*",
    ]
  }

  statement {
    sid     = "LogGroups"
    actions = ["logs:*"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/ranchhand-*",
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/ranchhand-*:*",
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/apigateway/ranchhand-*",
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/apigateway/ranchhand-*:*",
    ]
  }

  # API Gateway v2 IAM resources are path-based, so they cannot be scoped by API name.
  statement {
    sid       = "ApiGateway"
    actions   = ["apigateway:*"]
    resources = ["arn:aws:apigateway:${var.aws_region}::/*"]
  }

  # CreateUserPool cannot be scoped to a resource that does not exist yet.
  statement {
    sid       = "Cognito"
    actions   = ["cognito-idp:*"]
    resources = ["*"]
  }

  statement {
    sid = "ManageServiceRoles"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:PutRolePolicy",
      "iam:GetRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/ranchhand-*"]
  }

  statement {
    sid       = "PassServiceRoles"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/ranchhand-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "gha_apply" {
  name   = "terraform-apply"
  role   = aws_iam_role.gha_apply.id
  policy = data.aws_iam_policy_document.gha_apply.json
}

output "gha_plan_role_arn" {
  description = "Role for the workflow's terraform plan job."
  value       = aws_iam_role.gha_plan.arn
}

output "gha_apply_role_arn" {
  description = "Role for the workflow's terraform apply job."
  value       = aws_iam_role.gha_apply.arn
}
