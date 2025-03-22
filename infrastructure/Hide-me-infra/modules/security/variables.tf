/**
 * # Security Module Variables
 *
 * Variables for the security module of the Hide Me application.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region where resources will be created"
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

variable "private_subnet_ranges" {
  description = "CIDR ranges for private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24"]
}

variable "health_check_port" {
  description = "Port for health checks"
  type        = number
  default     = 8000
}

variable "backend_port" {
  description = "Port on which the backend instances serve HTTP traffic"
  type        = number
  default     = 8000
}

variable "db_user" {
  description = "Database user name"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Database user password"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Name of the database"
  type        = string
}
