/**
 * # Compute Module Variables
 *
 * Variables for the compute module of the Hide Me application.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region where resources will be created"
  type        = string
}


variable "zones" {
  description = "List of zones for regional instance group"
  type        = list(string)
  default     = []
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
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

variable "disk_type" {
  description = "Boot disk type, can be either pd-ssd, local-ssd, or pd-standard"
  type        = string
  default     = "pd-standard"
}

variable "network_id" {
  description = "The ID of the VPC network"
  type        = string
}

variable "subnet_id" {
  description = "The ID of the subnet"
  type        = string
}

variable "service_account_email" {
  description = "Email address of the service account"
  type        = string
}

variable "min_instances" {
  description = "Minimum number of instances in the instance group"
  type        = number
  default     = 2
}

variable "max_instances" {
  description = "Maximum number of instances in the instance group"
  type        = number
  default     = 5
}

variable "app_port" {
  description = "Port on which the application serves traffic"
  type        = number
  default     = 8000
}

variable "go_port" {
  description = "Port on which the Go application serves traffic"
  type        = number
  default     = 8080
}

variable "target_pools" {
  description = "List of target pool URLs to which instances in the group should be added"
  type        = list(string)
  default     = []
}

variable "db_connection_name" {
  description = "The connection name of the Cloud SQL instance"
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

variable "db_host" {
  description = "Database host address"
  type        = string
}

variable "db_port" {
  description = "Database port name"
  type        = string

}

variable "github_ssh_key" {
  description = "SSH private key for GitHub repository access"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_token" {
  description = "GitHub Personal Access Token for repository access (as fallback)"
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
  default     = ""
}

variable "go_github_repo" {
  description = "GitHub repository URL for the Go backend code"
  type        = string
  default     = ""
}

variable "github_branch" {
  description = "GitHub branch to deploy"
  type        = string
  default     = "main"
}

variable "repo_name" {
  description = "Name of the GitHub repository"
  type        = string
  default     = ""
}

variable "repo_owner" {
  description = "Owner of the GitHub repository"
  type        = string
  default     = ""
}

variable "domain" {
  description = "Domain name for the application"
  type        = string
  default = ""
}

variable "go_domain" {
  description = "Domain name for the Go application"
  type        = string
  default     = ""
}

variable "ssl_email" {
  description = "Email address for SSL certificate notifications"
  type        = string
}