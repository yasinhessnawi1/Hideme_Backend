/**
 * # Database Module Variables
 *
 * Variables for the database module of the Hide Me application.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region where the database will be created"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "network_id" {
  description = "The ID of the VPC network"
  type        = string
}

variable "private_subnet_cidr" {
  description = "The CIDR range of the private subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "db_instance_name" {
  description = "Name for the database instance"
  type        = string
}

variable "db_version" {
  description = "Database version"
  type        = string
  default     = "POSTGRES_14"
}

variable "db_tier" {
  description = "Machine tier for the database instance"
  type        = string
}

variable "db_disk_size" {
  description = "Disk size for the database in GB"
  type        = number
  default     = 50
  validation {
    condition     = var.db_disk_size >= 10 && var.db_disk_size <= 4000
    error_message = "Database disk size must be between 10 and 4000 GB."
  }
}

variable "db_name" {
  description = "Name of the database to create"
  type        = string
}

variable "db_user" {
  description = "Database user name"
  type        = string
}

variable "db_password" {
  description = "Database user password"
  type        = string
  sensitive   = true
}

variable "db_deletion_protection" {
  description = "Whether to enable deletion protection for the database"
  type        = bool
  default     = true
}
