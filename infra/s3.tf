locals {
  frontend_bucket = "ranchhand-frontend-${local.account_id}"
  frontend_origin = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

resource "aws_s3_bucket" "frontend" {
  bucket = local.frontend_bucket
}

# Private by default: every apply (each deploy from main) re-blocks public access.
# To test, turn off "Block all public access" in the console and add a public-read
# bucket policy (see docs/setup.rst). That policy is deliberately not managed here, so
# it persists but stays inert while the block is on.
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }
}
