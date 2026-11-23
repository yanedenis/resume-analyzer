provider "aws" {
  region = var.aws_region
}

# 1. S3 Bucket for Resume Uploads & Static Frontend
resource "aws_s3_bucket" "app_bucket" {
  bucket        = "resume-analyzer-storage-${var.aws_region}"
  force_destroy = true
}

resource "aws_s3_bucket_cors_configuration" "cors" {
  bucket = aws_s3_bucket.app_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}

# 2. DynamoDB Table for Storing Analysis Results
resource "aws_dynamodb_table" "results_table" {
  name         = "ResumeAnalysisResults"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "resume_id"

  attribute {
    name = "resume_id"
    type = "S"
  }
}

# 3. IAM Role for Lambda Execution
resource "aws_iam_role" "lambda_role" {
  name = "resume_analyzer_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_custom" {
  name = "resume_analyzer_custom_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.app_bucket.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.results_table.arn
      }
    ]
  })
}

# 4. Lambda Function for Processing Resumes
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/application-code"
  output_path = "${path.module}/lambda.zip"
}

# Third-party dependencies (google-genai etc.) live in a layer, built by
# `python scripts/build_layer.py` into build/layer/python
data "archive_file" "deps_layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../build/layer"
  output_path = "${path.module}/deps_layer.zip"
}

resource "aws_lambda_layer_version" "deps" {
  layer_name          = "resume-analyzer-deps"
  filename            = data.archive_file.deps_layer_zip.output_path
  source_code_hash    = data.archive_file.deps_layer_zip.output_base64sha256
  compatible_runtimes = ["python3.11"]
}

resource "aws_lambda_function" "analyzer_lambda" {
  layers           = [aws_lambda_layer_version.deps.arn]
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "ResumeAnalyzerFunction"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 120
  memory_size      = 512
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      GEMINI_API_KEY      = var.gemini_api_key
      GEMINI_MODELS       = "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite"
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.results_table.name
    }
  }
}

# Don't let AWS silently re-run a failed/timed-out analysis (S3 invokes async)
resource "aws_lambda_function_event_invoke_config" "analyzer_no_retry" {
  function_name          = aws_lambda_function.analyzer_lambda.function_name
  maximum_retry_attempts = 0
}

# 5. S3 Trigger to Invoke Lambda on Upload
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.app_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.analyzer_lambda.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_prefix       = "uploads/"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.analyzer_lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.app_bucket.arn
}