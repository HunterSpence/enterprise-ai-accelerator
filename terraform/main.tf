# Enterprise AI Accelerator — Root Terraform Module
# Deploys to any combination of AWS, Azure, GCP, and OCI
# controlled by var.enabled_clouds
#
# Usage examples:
#   Single cloud (AWS):
#     terraform apply -var='enabled_clouds=["aws"]'
#
#   Multi-cloud assessment (all four):
#     terraform apply -var='enabled_clouds=["aws","azure","gcp","oci"]'
#
#   Cross-cloud migration (source=AWS, target=OCI):
#     terraform apply \
#       -var='enabled_clouds=["aws","oci"]' \
#       -var='source_cloud=aws' \
#       -var='target_cloud=oci'

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Provider configurations (only active when included in enabled_clouds)
# ---------------------------------------------------------------------------

provider "aws" {
  region = var.aws_region
}

provider "azurerm" {
  features {}
  subscription_id = var.azure_subscription_id
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

provider "oci" {
  tenancy_ocid     = var.oci_tenancy_ocid
  user_ocid        = var.oci_user_ocid
  fingerprint      = var.oci_fingerprint
  private_key_path = var.oci_private_key_path
  region           = var.oci_region
}

# ---------------------------------------------------------------------------
# AWS module (enabled when "aws" is in enabled_clouds)
# ---------------------------------------------------------------------------

module "aws" {
  count  = contains(var.enabled_clouds, "aws") ? 1 : 0
  source = "./modules/aws"

  region        = var.aws_region
  environment   = var.environment
  project_name  = var.project_name
  vpc_cidr      = var.aws_vpc_cidr
  instance_type = var.aws_instance_type
  db_class      = var.aws_db_instance_class
}

# ---------------------------------------------------------------------------
# Azure module (enabled when "azure" is in enabled_clouds)
# ---------------------------------------------------------------------------

module "azure" {
  count  = contains(var.enabled_clouds, "azure") ? 1 : 0
  source = "./modules/azure"

  location     = var.azure_location
  environment  = var.environment
  project_name = var.project_name
  vnet_cidr    = var.azure_vnet_cidr
  vm_size      = var.azure_vm_size
}

# ---------------------------------------------------------------------------
# GCP module (enabled when "gcp" is in enabled_clouds)
# ---------------------------------------------------------------------------

module "gcp" {
  count  = contains(var.enabled_clouds, "gcp") ? 1 : 0
  source = "./modules/gcp"

  project_id   = var.gcp_project_id
  region       = var.gcp_region
  zone         = var.gcp_zone
  environment  = var.environment
  project_name = var.project_name
  subnet_cidr  = var.gcp_vpc_cidr
  machine_type = var.gcp_machine_type
}

# ---------------------------------------------------------------------------
# OCI module (enabled when "oci" is in enabled_clouds)
# ---------------------------------------------------------------------------

module "oci" {
  count  = contains(var.enabled_clouds, "oci") ? 1 : 0
  source = "./modules/oci"

  tenancy_ocid  = var.oci_tenancy_ocid
  region        = var.oci_region
  environment   = var.environment
  project_name  = var.project_name
  vcn_cidr      = var.oci_vcn_cidr
  shape         = var.oci_shape
  ocpus         = var.oci_ocpus
  memory_gb     = var.oci_memory_gb
}
