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

# New variables for CIDR ranges to address security concerns

variable "health_check_ip_ranges" {
  description = "Google Cloud's health check IP ranges"
  type        = list(string)
  default = [
    "35.191.0.0/16",
    "130.211.0.0/22",
    "209.85.152.0/22",
    "209.85.204.0/22"
  ]
}

variable "iap_ip_ranges" {
  description = "Google's Identity-Aware Proxy IP ranges"
  type        = list(string)
  default     = ["35.235.240.0/20"]
}

variable "load_balancer_ip_ranges" {
  description = "Google Cloud's load balancer IP ranges"
  type        = list(string)
  default = [
    "130.211.0.0/22",
    "35.191.0.0/16"
  ]
}

variable "google_api_ranges" {
  description = "Google API IP ranges"
  type        = list(string)
  default = [
    "199.36.153.8/30", # Restricted Google APIs
    "199.36.153.4/30"  # Private Google Access
  ]
}

variable "allowed_ip_ranges" {
  description = "IP ranges allowed to access the application (empty means all)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}