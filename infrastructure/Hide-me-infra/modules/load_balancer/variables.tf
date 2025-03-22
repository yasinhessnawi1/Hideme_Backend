/**
 * # Load Balancer Module Variables
 *
 * Variables for the load balancer module of the Hide Me application.
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

variable "instance_group" {
  description = "The instance group to be used as backend for the load balancer"
  type        = string
}

variable "backend_port" {
  description = "Port on which the backend instances serve HTTP traffic"
  type        = number
  default     = 8000
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
}

variable "enable_ssl" {
  description = "Whether to enable HTTPS with SSL certificates"
  type        = bool
  default     = true
}

variable "security_policy_name" {
  description = "Name of the Cloud Armor security policy to attach to the load balancer"
  type        = string
  default     = ""
}