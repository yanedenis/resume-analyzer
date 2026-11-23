output "s3_bucket_name" {
  value = aws_s3_bucket.app_bucket.id
}

output "lambda_function_name" {
  value = aws_lambda_function.analyzer_lambda.function_name
}

output "api_url" {
  description = "Paste this into API_URL in frontend/index.html"
  value       = aws_lambda_function_url.api.function_url
}