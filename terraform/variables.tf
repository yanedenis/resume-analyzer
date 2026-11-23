variable "aws_region" {
  default     = "eu-north-1"
  description = "AWS Region for deployment"
}

variable "gemini_api_key" {
  type        = string
  description = "Google Gemini API Key"
  sensitive   = true
}