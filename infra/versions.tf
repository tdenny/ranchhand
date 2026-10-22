terraform {
  required_version = ">= 1.10"

  backend "s3" {
    # bucket is supplied at init time: terraform init -backend-config=backend.hcl
    key          = "ranchhand/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}
