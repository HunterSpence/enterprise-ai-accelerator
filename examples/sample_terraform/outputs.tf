output "s3_bucket_name" {
  description = "Name of the S3 bucket (public-read — demo only)"
  value       = aws_s3_bucket.public_data.bucket
}

output "rds_endpoint" {
  description = "RDS instance endpoint (publicly accessible — demo only)"
  value       = aws_db_instance.app_db.endpoint
  sensitive   = true
}

output "kms_key_arn" {
  description = "ARN of the KMS key (rotation disabled — demo only)"
  value       = aws_kms_key.app_key.arn
}

output "security_group_id" {
  description = "ID of the bastion security group (open SSH — demo only)"
  value       = aws_security_group.bastion.id
}
