plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# Needs `tflint --init` to download the plugin. Bump the version deliberately.
plugin "aws" {
  enabled = true
  version = "0.50.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
