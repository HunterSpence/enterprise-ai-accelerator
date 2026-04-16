# CloudIQ — OCI Terraform Module
# Provisions the landing zone for the Enterprise AI Accelerator on Oracle Cloud.

variable "tenancy_ocid" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "project_name" { type = string }
variable "vcn_cidr" { type = string }
variable "shape" { type = string }
variable "ocpus" { type = number }
variable "memory_gb" { type = number }

# Fetch availability domains
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

locals {
  first_ad = data.oci_identity_availability_domains.ads.availability_domains[0].name
  common_freeform_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Module      = "enterprise-ai-accelerator/oci"
  }
}

# VCN (Virtual Cloud Network)
resource "oci_core_vcn" "main" {
  cidr_block     = var.vcn_cidr
  compartment_id = var.tenancy_ocid
  display_name   = "${var.project_name}-vcn"
  dns_label      = replace(var.project_name, "-", "")
  freeform_tags  = local.common_freeform_tags
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = var.tenancy_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-igw"
  freeform_tags  = local.common_freeform_tags
}

resource "oci_core_route_table" "public" {
  compartment_id = var.tenancy_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.main.id
  }

  freeform_tags = local.common_freeform_tags
}

resource "oci_core_security_list" "api" {
  compartment_id = var.tenancy_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-api-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  ingress_security_rules {
    protocol = "6"  # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 8001
      max = 8005
    }
  }

  ingress_security_rules {
    protocol = "6"  # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 22
      max = 22
    }
  }

  freeform_tags = local.common_freeform_tags
}

resource "oci_core_subnet" "public" {
  cidr_block        = cidrsubnet(var.vcn_cidr, 8, 1)
  compartment_id    = var.tenancy_ocid
  vcn_id            = oci_core_vcn.main.id
  display_name      = "${var.project_name}-public-subnet"
  dns_label         = "public"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.api.id]
  freeform_tags     = local.common_freeform_tags
}

# Compute instance
data "oci_core_images" "oracle_linux" {
  compartment_id           = var.tenancy_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = "9"
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_instance" "api" {
  availability_domain = local.first_ad
  compartment_id      = var.tenancy_ocid
  shape               = var.shape
  display_name        = "${var.project_name}-api"

  shape_config {
    ocpus         = var.ocpus
    memory_in_gbs = var.memory_gb
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.oracle_linux.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    display_name     = "${var.project_name}-api-vnic"
  }

  metadata = {
    user_data = base64encode(<<-EOF
      #!/bin/bash
      dnf install -y python3.11 git
      git clone https://github.com/HunterSpence/enterprise-ai-accelerator /opt/eaa
      cd /opt/eaa && pip3 install -r requirements.txt
    EOF
    )
  }

  freeform_tags = local.common_freeform_tags
}

# Object Storage bucket
data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.tenancy_ocid
}

resource "oci_objectstorage_bucket" "data" {
  compartment_id = var.tenancy_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${var.project_name}-data-${var.environment}"
  access_type    = "NoPublicAccess"
  versioning     = "Enabled"
  freeform_tags  = local.common_freeform_tags
}

output "vcn_id" { value = oci_core_vcn.main.id }
output "instance_public_ip" {
  value = oci_core_instance.api.public_ip
}
output "object_storage_bucket" { value = oci_objectstorage_bucket.data.name }
