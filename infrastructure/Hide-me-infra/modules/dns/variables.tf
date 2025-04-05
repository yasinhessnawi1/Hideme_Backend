/**
 * # DNS Module Variables
 *
 * Variables for the DNS module of the Hide Me application.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "domain_name" {
  description = "The root domain name without trailing dot (e.g., hidemeai.com)"
  type        = string
  default = "hidemeai.com"
}

variable "load_balancer_ip" {
  description = "The static IP address of the load balancer"
  type        = string
}