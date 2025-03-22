/**
 * # VPC Module Variables
 *
 * Variables for the VPC module of the Hide Me application.
 */

variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region where resources will be created"
  type        = string
}

variable "network_name" {
  description = "Name of the VPC network"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "public_subnet_cidr" {
  description = "CIDR range for the public subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR range for the private subnet"
  type        = string
  default     = "10.0.1.0/24"
}
