# CloudIQ — GCP Terraform Module
# Provisions the landing zone for the Enterprise AI Accelerator on Google Cloud.

variable "project_id" { type = string }
variable "region" { type = string }
variable "zone" { type = string }
variable "environment" { type = string }
variable "project_name" { type = string }
variable "subnet_cidr" { type = string }
variable "machine_type" { type = string }

locals {
  common_labels = {
    project     = replace(var.project_name, "-", "_")
    environment = var.environment
    managed_by  = "terraform"
    module      = "enterprise-ai-accelerator-gcp"
  }
}

# Enable required APIs
resource "google_project_service" "compute" {
  service = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "sqladmin" {
  service = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

# VPC Network
resource "google_compute_network" "main" {
  name                    = "${var.project_name}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.compute]
}

resource "google_compute_subnetwork" "public" {
  name          = "${var.project_name}-public-subnet"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.main.id
}

# Firewall rules
resource "google_compute_firewall" "api" {
  name    = "${var.project_name}-allow-api"
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["8001", "8002", "8003", "8004", "8005", "22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["eaa-api"]
}

# Compute Engine instance
resource "google_compute_instance" "api" {
  name         = "${var.project_name}-api"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["eaa-api"]

  boot_disk {
    initialize_params {
      image  = "debian-cloud/debian-12"
      size   = 50
      type   = "pd-balanced"
    }
  }

  network_interface {
    network    = google_compute_network.main.name
    subnetwork = google_compute_subnetwork.public.name
    access_config {}  # Ephemeral public IP
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    apt-get update -y
    apt-get install -y python3.11 python3-pip git
    git clone https://github.com/HunterSpence/enterprise-ai-accelerator /opt/eaa
    cd /opt/eaa && pip3 install -r requirements.txt
  EOF

  service_account {
    email  = google_service_account.api.email
    scopes = ["cloud-platform"]
  }

  labels = local.common_labels

  depends_on = [google_project_service.compute]
}

# Service Account
resource "google_service_account" "api" {
  account_id   = "${replace(var.project_name, "-", "-")}sa"
  display_name = "Enterprise AI Accelerator Service Account"
}

resource "google_project_iam_member" "viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Cloud Storage bucket
resource "google_storage_bucket" "data" {
  name     = "${var.project_name}-data-${var.environment}-${var.project_id}"
  location = var.region
  labels   = local.common_labels

  versioning { enabled = true }

  lifecycle_rule {
    condition { age = 365 }
    action { type = "SetStorageClass"; storage_class = "NEARLINE" }
  }
}

output "instance_external_ip" {
  value = google_compute_instance.api.network_interface[0].access_config[0].nat_ip
}
output "gcs_bucket_name" { value = google_storage_bucket.data.name }
