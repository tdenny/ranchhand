output "api_endpoint" {
  description = "Base URL of the API; set as the API_BASE_URL repository variable for the frontend deploy."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "frontend_bucket" {
  description = "Bucket the frontend deploy job syncs to; set as the FRONTEND_BUCKET repository variable."
  value       = aws_s3_bucket.frontend.id
}

output "frontend_url" {
  description = "Public URL of the frontend."
  value       = local.frontend_origin
}
