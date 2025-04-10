/**
 * # Load Balancer Module Variables
 *
 * Variables for the load balancer module of the Hide Me application.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}



variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "lb_timeout_sec" {
  description = "Timeout in seconds for the load balancer backend service"
  type        = number
  default     = 1800  # 30 minutes for long-running requests
}

variable "lb_connection_draining_timeout_sec" {
  description = "Connection draining timeout in seconds for the load balancer backend service"
  type        = number
  default     = 600   # 10 minutes for connection draining
}

variable "instance_group" {
  description = "The instance group to be used as backend for the load balancer"
  type        = string
}


variable "health_check_port" {
  description = "Port for health checks"
  type        = number
  default     = 8000
}

variable "static_ip_name" {
  description = "Name for the static IP address resource"
  type        = string
}

variable "domain_name" {
  description = "Root domain name without trailing dot (e.g., hidemeai.com)"
  type        = string
  default = "hidemeai.com"
}


variable "security_policy_name" {
  description = "Name of the Cloud Armor security policy to attach to the load balancer"
  type        = string
  default     = ""
}