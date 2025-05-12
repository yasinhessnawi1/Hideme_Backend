/**
 * # Monitoring Module Variables
 *
 * Variables for the monitoring module of the Hide Me application.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region where resources will be created"
  type        = string
  default     = "europe-west4"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "instance_ids" {
  description = "List of instance IDs to monitor"
  type        = list(string)
}

variable "db_instance" {
  description = "The database instance name to monitor"
  type        = string
}

variable "lb_name" {
  description = "The name of the load balancer to monitor"
  type        = string
}

variable "alert_email" {
  description = "Email address to send monitoring alerts to"
  type        = string
  default     = ""
}
