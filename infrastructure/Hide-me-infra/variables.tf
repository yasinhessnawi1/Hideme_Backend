/**
 * # Variables for Hide Me Infrastructure
 *
 * This file contains all the input variables for the Hide Me application infrastructure.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region where resources will be created"
  type        = string
}

variable "zone" {
  description = "The GCP zone for zonal resources"
  type        = string
}

variable "credentials_file" {
  description = "Path to the GCP service account credentials file"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "network_name" {
  description = "Name of the VPC network"
  type        = string
}

variable "instance_name" {
  description = "Base name for compute instances"
  type        = string
}

variable "machine_type" {
  description = "Machine type for compute instances"
  type        = string
}

variable "disk_size" {
  description = "Boot disk size in GB"
  type        = number
}

variable "db_port" {
  description = "Database port"
  type        = number
  default     = 5432
}
variable "db_disk_size" {
  description = "Boot disk size in GB"
  type        = number
  default     = 10
}

variable "disk_type" {
  description = "Boot disk type, can be either pd-ssd, local-ssd, or pd-standard"
  type        = string
  default     = "pd-standard"
}

variable "min_instances" {
  description = "Minimum number of instances in the instance group"
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum number of instances in the instance group"
  type        = number
  default     = 5
}

variable "backend_port" {
  description = "Port on which the backend serves HTTP traffic"
  type        = number
  default     = 8000
}

variable "go_backend_port" {
  description = "Port on which the Go backend serves HTTP traffic"
  type        = number
  default     = 8080
}

variable "health_check_port" {
  description = "Port for health checks"
  type        = number
  default     = 8000
}

variable "enable_ssl" {
  description = "Whether to enable HTTPS with SSL certificates"
  type        = bool
  default     = false
}


variable "db_instance_name" {
  description = "Name for the database instance"
  type        = string
}

variable "db_version" {
  description = "Database engine version"
  type        = string
}

variable "db_tier" {
  description = "Machine type for the database instance"
  type        = string
}

variable "db_name" {
  description = "Name of the database"
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
  default     = false
}

variable "alert_email" {
  description = "Email address to send monitoring alerts to"
  type        = string
  default     = ""
}

variable "github_ssh_key" {
  description = "SSH private key for GitHub repository access"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "API key for Gemini AI services"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_repo" {
  description = "GitHub repository URL for the backend code"
  type        = string
  default     = "git@github.com:yasinhessnawi1/Hideme_Backend.git"
}

variable "go_github_repo" {
  description = "GitHub repository URL for the Go backend code"
  type        = string
  default     = "git@github.com:yasinhessnawi1/Hideme_Backend.git"
}

variable "github_branch" {
  description = "GitHub branch to deploy"
  type        = string
  default     = "main"
}

variable "github_token" {
  description = "GitHub Personal Access Token for repository access (as fallback)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "repo_name" {
  description = "Name of the GitHub repository"
  type        = string
  default     = "Hideme_Backend"
}

variable "repo_owner" {
  description = "Owner of the GitHub repository"
  type        = string
  default     = "yasinhessnawi1"
}

variable "domain" {
  description = "Domain name for the application"
  type        = string
}

variable "db_host" {
  description = "Database IP address to associate with the database"
  type        = string
  default     = "10.25.0.2"
}
variable "go_domain" {
  description = "Domain name for the Go application"
  type        = string
  default     = "goapi.hidemeai.com"
}

variable "ssl_email" {
  description = "Email address for SSL certificate notifications"
  type        = string
}

variable "static_ip_name" {
  description = "Name for the static IP address resource"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the Google-managed SSL certificate"
  type        = string
  default     = "hidemeai.com"
}