# CloudIQ — Azure Terraform Module
# Provisions the landing zone for the Enterprise AI Accelerator on Azure.

variable "location" { type = string }
variable "environment" { type = string }
variable "project_name" { type = string }
variable "vnet_cidr" { type = string }
variable "vm_size" { type = string }

locals {
  rg_name = "${var.project_name}-${var.environment}-rg"
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Module      = "enterprise-ai-accelerator/azure"
  }
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = local.rg_name
  location = var.location
  tags     = local.common_tags
}

# Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = "${var.project_name}-vnet"
  address_space       = [var.vnet_cidr]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_subnet" "public" {
  name                 = "${var.project_name}-public-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 1)]
}

resource "azurerm_subnet" "private" {
  name                 = "${var.project_name}-private-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 10)]
}

# Public IP
resource "azurerm_public_ip" "api" {
  name                = "${var.project_name}-api-pip"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags
}

# Network Interface
resource "azurerm_network_interface" "api" {
  name                = "${var.project_name}-api-nic"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.public.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.api.id
  }

  tags = local.common_tags
}

# Network Security Group
resource "azurerm_network_security_group" "api" {
  name                = "${var.project_name}-api-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "AllowAPIports"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["8001", "8002", "8003", "8004", "8005"]
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowSSH"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.common_tags
}

resource "azurerm_network_interface_security_group_association" "api" {
  network_interface_id      = azurerm_network_interface.api.id
  network_security_group_id = azurerm_network_security_group.api.id
}

# Linux VM
resource "azurerm_linux_virtual_machine" "api" {
  name                = "${var.project_name}-api-vm"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.vm_size
  admin_username      = "azureuser"

  network_interface_ids = [azurerm_network_interface.api.id]

  admin_ssh_key {
    username   = "azureuser"
    public_key = file("~/.ssh/id_rsa.pub")
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  custom_data = base64encode(<<-EOF
    #!/bin/bash
    apt-get update -y
    apt-get install -y python3.11 python3-pip git
    git clone https://github.com/HunterSpence/enterprise-ai-accelerator /opt/eaa
    cd /opt/eaa && pip3 install -r requirements.txt
  EOF
  )

  tags = local.common_tags
}

# Storage Account
resource "azurerm_storage_account" "data" {
  name                     = "${replace(var.project_name, "-", "")}data${var.environment}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = local.common_tags
}

resource "azurerm_storage_container" "audit" {
  name                  = "audit-trail"
  storage_account_name  = azurerm_storage_account.data.name
  container_access_type = "private"
}

output "resource_group_name" { value = azurerm_resource_group.main.name }
output "vm_public_ip" { value = azurerm_public_ip.api.ip_address }
output "storage_account_name" { value = azurerm_storage_account.data.name }
