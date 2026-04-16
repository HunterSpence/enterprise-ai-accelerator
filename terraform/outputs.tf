# Enterprise AI Accelerator — Unified Terraform Outputs
# All outputs are optional (null when the module is disabled)

output "enabled_clouds" {
  description = "Which cloud providers were deployed"
  value       = var.enabled_clouds
}

output "source_cloud" {
  description = "Cloud being migrated from (for cross-cloud plans)"
  value       = var.source_cloud
}

output "target_cloud" {
  description = "Cloud being migrated to (empty = single-cloud assessment)"
  value       = var.target_cloud
}

# AWS outputs
output "aws_vpc_id" {
  description = "AWS VPC ID"
  value       = length(module.aws) > 0 ? module.aws[0].vpc_id : null
}

output "aws_instance_public_ip" {
  description = "AWS API server public IP"
  value       = length(module.aws) > 0 ? module.aws[0].instance_public_ip : null
  sensitive   = false
}

output "aws_s3_bucket" {
  description = "AWS S3 bucket name for accelerator data"
  value       = length(module.aws) > 0 ? module.aws[0].s3_bucket_name : null
}

# Azure outputs
output "azure_resource_group" {
  description = "Azure resource group name"
  value       = length(module.azure) > 0 ? module.azure[0].resource_group_name : null
}

output "azure_vm_public_ip" {
  description = "Azure VM public IP"
  value       = length(module.azure) > 0 ? module.azure[0].vm_public_ip : null
}

output "azure_storage_account" {
  description = "Azure storage account name"
  value       = length(module.azure) > 0 ? module.azure[0].storage_account_name : null
}

# GCP outputs
output "gcp_instance_external_ip" {
  description = "GCP Compute Engine external IP"
  value       = length(module.gcp) > 0 ? module.gcp[0].instance_external_ip : null
}

output "gcp_gcs_bucket" {
  description = "GCP Cloud Storage bucket name"
  value       = length(module.gcp) > 0 ? module.gcp[0].gcs_bucket_name : null
}

# OCI outputs
output "oci_instance_public_ip" {
  description = "OCI compute instance public IP"
  value       = length(module.oci) > 0 ? module.oci[0].instance_public_ip : null
}

output "oci_vcn_id" {
  description = "OCI VCN ID"
  value       = length(module.oci) > 0 ? module.oci[0].vcn_id : null
}

output "oci_object_storage_bucket" {
  description = "OCI Object Storage bucket name"
  value       = length(module.oci) > 0 ? module.oci[0].object_storage_bucket : null
}
