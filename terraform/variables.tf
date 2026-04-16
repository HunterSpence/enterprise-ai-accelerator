variable "enabled_clouds" {
  description = "List of cloud providers to enable. Valid values: aws, azure, gcp, oci"
  type        = list(string)
  default     = ["aws"]
  validation {
    condition     = alltrue([for c in var.enabled_clouds : contains(["aws", "azure", "gcp", "oci"], c)])
    error_message = "Valid cloud values are: aws, azure, gcp, oci."
  }
}

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
}

variable "azure_location" {
  description = "Azure region for resource deployment"
  type        = string
  default     = "eastus"
}

variable "gcp_project" {
  description = "GCP project ID"
  type        = string
  default     = ""
}

variable "gcp_region" {
  description = "GCP region for resource deployment"
  type        = string
  default     = "us-central1"
}

variable "oci_region" {
  description = "OCI region identifier"
  type        = string
  default     = "us-ashburn-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}
