variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "europe-west4"
}


variable "instance_zone" {
  description = "The zone where the backend instance is located"
  type        = string
}

variable "instance_self_link" {
  description = "The self link of the compute instance to add to the backend"
  type        = string
}

variable "instance_name" {
  description = "The name of the compute instance"
  type        = string
}

variable "backend_port" {
  description = "The port on which the backend instance is serving HTTP traffic"
  type        = number
  default     = 80
}
