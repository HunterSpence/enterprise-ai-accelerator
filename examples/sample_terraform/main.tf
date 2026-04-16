# sample_terraform/main.tf
# ========================
# DEMO ONLY — violations are intentional so iac_security scanner has findings.
# See README.md for the full list of flagged policy IDs.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# IAC-001: S3 bucket with public-read ACL
# Violation: data exfiltration risk — bucket contents readable by anyone
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "public_data" {
  bucket = var.public_bucket_name
  acl    = "public-read"

  tags = {
    Environment = var.environment
    Team        = "platform"
  }
}

# ---------------------------------------------------------------------------
# IAC-006: EBS volume without encryption
# Violation: data at rest not protected
# ---------------------------------------------------------------------------
resource "aws_ebs_volume" "app_data" {
  availability_zone = "us-east-1a"
  size              = 100
  type              = "gp3"
  encrypted         = false

  tags = {
    Name        = "app-data-volume"
    Environment = var.environment
  }
}

# ---------------------------------------------------------------------------
# IAC-013: Security group with unrestricted SSH ingress (0.0.0.0/0 port 22)
# Violation: any internet host can attempt SSH connections
# ---------------------------------------------------------------------------
resource "aws_security_group" "bastion" {
  name        = "bastion-sg"
  description = "Security group for bastion host"
  vpc_id      = var.vpc_id

  ingress {
    description = "SSH from anywhere"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "bastion-sg"
  }
}

# ---------------------------------------------------------------------------
# IAC-014: IAM policy with wildcard Action and Resource
# Violation: grants full AWS access — violates least-privilege principle
# ---------------------------------------------------------------------------
resource "aws_iam_policy" "overprivileged" {
  name        = "overprivileged-app-policy"
  description = "Application policy — do not use in production"

  policy = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"*\"],\"Resource\":[\"*\"]}]}"
}

# ---------------------------------------------------------------------------
# IAC-010: RDS instance publicly accessible
# Violation: database endpoint reachable from public internet
# ---------------------------------------------------------------------------
resource "aws_db_instance" "app_db" {
  identifier        = "app-postgres"
  engine            = "postgres"
  engine_version    = "14.9"
  instance_class    = var.db_instance_class
  allocated_storage = 20
  storage_type      = "gp2"

  db_name  = "appdb"
  username = var.db_username
  password = var.db_password

  publicly_accessible = true
  storage_encrypted   = false

  skip_final_snapshot = true

  tags = {
    Environment = var.environment
  }
}

# ---------------------------------------------------------------------------
# IAC-017: CloudTrail without log file validation
# Violation: audit logs could be tampered with silently
# ---------------------------------------------------------------------------
resource "aws_cloudtrail" "main" {
  name                          = "main-trail"
  s3_bucket_name                = aws_s3_bucket.public_data.id
  include_global_service_events = true
  is_multi_region_trail         = false
  enable_log_file_validation    = false

  tags = {
    Environment = var.environment
  }
}

# ---------------------------------------------------------------------------
# IAC-016: KMS key without automatic rotation
# Violation: long-lived keys increase blast radius if compromised
# ---------------------------------------------------------------------------
resource "aws_kms_key" "app_key" {
  description             = "Application encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = false

  tags = {
    Environment = var.environment
  }
}

resource "aws_kms_alias" "app_key_alias" {
  name          = "alias/app-key"
  target_key_id = aws_kms_key.app_key.key_id
}
