data "archive_file" "api" {
  type        = "zip"
  source_dir  = "${path.module}/.build/package"
  output_path = "${path.module}/.build/api.zip"
  excludes    = ["**/__pycache__/**"]
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/ranchhand-api"
  retention_in_days = 30
}

resource "aws_lambda_function" "api" {
  function_name = "ranchhand-api"
  role          = aws_iam_role.api.arn
  runtime       = "python3.13"
  architectures = ["arm64"]
  handler       = "ranchhand.handler.handler"
  memory_size   = 256
  timeout       = 10

  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.herd.name
      LOG_LEVEL  = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.api]
}
