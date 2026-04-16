# Enterprise AI Accelerator — Terraform Variables
# Covers AWS, Azure, GCP, and OCI in a single variable file.

variable "enabled_clouds" {
  description = "List of cloud providers to deploy to. Valid values: aws, azure, gcp, oci"
  type        = list(string)
  default     = ["aws"]

  validation {
    condition = alltrue([
      for c in var.enabled_clouds : contains(["aws", "azure", "gcp", "oci"], c)
    ])
    error_message = "enabled_clouds must contain only: aws, azure, gcp, oci"
  }
}

variable "source_cloud" {
  description = "Cloud being migrated FROM (for cross-cloud planning)"
  type        = string
  default     = "aws"
}

variable "target_cloud" {
  description = "Cloud being migrated TO. Empty string = single-cloud assessment."
  type        = string
  default     = ""
}

variable "environment" {
  description = "Deployment environment tag (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name used for resource naming and tags"
  type        = string
  default     = "enterprise-ai-accelerator"
}

# ---------------------------------------------------------------------------
# AWS variables
# ---------------------------------------------------------------------------
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_instance_type" {
  description = "EC2 instance type for the accelerator API server"
  type        = string
  default     = "t3.medium"
}

variable "aws_vpc_cidr" {
  description = "CIDR block for the AWS VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "aws_db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

# ---------------------------------------------------------------------------
# Azure variables
# ---------------------------------------------------------------------------
variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
  default     = ""
  sensitive   = true
}

variable "azure_location" {
  description = "Azure region"
  type        = string
  default     = "East US"
}

variable "azure_vm_size" {
  description = "Azure VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "azure_vnet_cidr" {
  description = "CIDR for Azure VNet"
  type        = string
  default     = "10.1.0.0/16"
}

# ---------------------------------------------------------------------------
# GCP variables
# ---------------------------------------------------------------------------
variable "gcp_project_id" {
  description = "Google Cloud project ID"
  type        = string
  default     = ""
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "gcp_zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "gcp_machine_type" {
  description = "Compute Engine machine type"
  type        = string
  default     = "e2-medium"
}

variable "gcp_vpc_cidr" {
  description = "CIDR for GCP VPC subnet"
  type        = string
  default     = "10.2.0.0/16"
}

# ---------------------------------------------------------------------------
# OCI variables
# ---------------------------------------------------------------------------
variable "oci_tenancy_ocid" {
  description = "OCI tenancy OCID"
  type        = string
  default     = ""
  sensitive   = true
}

variable "oci_user_ocid" {
  description = "OCI user OCID"
  type        = string
  default     = ""
  sensitive   = true
}

variable "oci_fingerprint" {
  description = "OCI API key fingerprint"
  type        = string
  default     = ""
  sensitive   = true
}

variable "oci_private_key_path" {
  description = "Path to OCI API private key PEM file"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "oci_region" {
  description = "OCI region"
  type        = string
  default     = "us-ashburn-1"
}

variable "oci_shape" {
  description = "OCI compute instance shape"
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "oci_ocpus" {
  description = "OCPUs for Flex shape"
  type        = number
  default     = 2
}

variable "oci_memory_gb" {
  description = "Memory in GB for Flex shape"
  type        = number
  default     = 16
}

variable "oci_vcn_cidr" {
  description = "CIDR for OCI VCN"
  type        = string
  default     = "10.3.0.0/16"
}
