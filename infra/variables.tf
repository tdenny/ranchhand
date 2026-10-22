variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-2"
}

variable "github_repository" {
  description = "GitHub repository (owner/name) whose workflows may assume the CI roles."
  type        = string
}

variable "github_owner_id" {
  description = "Numeric ID of the GitHub user or organization that owns the repository."
  type        = string
}

variable "github_repository_id" {
  description = "Numeric ID of the GitHub repository."
  type        = string
}

variable "tf_state_bucket" {
  description = "Name of the S3 bucket holding Terraform state."
  type        = string
}
