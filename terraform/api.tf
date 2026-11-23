# API for the frontend: presigned upload URLs + result lookup,
# exposed through a Lambda Function URL (no API Gateway needed).

data "archive_file" "api_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/api-code"
  output_path = "${path.module}/api_lambda.zip"
}

# Reuses the existing role: it already allows s3:PutObject on the bucket
# and dynamodb:GetItem on the results table.
resource "aws_lambda_function" "api_lambda" {
  filename         = data.archive_file.api_zip.output_path
  function_name    = "ResumeAnalyzerApi"
  role             = aws_iam_role.lambda_role.arn
  handler          = "api_handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 10
  source_code_hash = data.archive_file.api_zip.output_base64sha256

  environment {
    variables = {
      BUCKET_NAME         = aws_s3_bucket.app_bucket.id
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.results_table.name
    }
  }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api_lambda.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST"]
    allow_headers = ["content-type"]
    max_age       = 3000
  }
}

# Public access to the Function URL needs BOTH permissions
resource "aws_lambda_permission" "api_url_public" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api_lambda.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "api_invoke_public" {
  statement_id             = "AllowPublicInvokeViaUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api_lambda.function_name
  principal                = "*"
  invoked_via_function_url = true
}