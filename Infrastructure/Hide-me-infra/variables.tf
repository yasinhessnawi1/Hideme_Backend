variable "project" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "europe-west4"
}

variable "zone" {
  description = "The GCP zone"
  type        = string
  default     = "europe-west4-c"
}

variable "credentials_file" {
  description = "Path to the GCP credentials JSON file"
  type        = string
}

variable "network_name" {
  description = "The name of the VPC network"
  type        = string
  default     = "terraform-vpc"
}

variable "instance_name" {
  description = "The name of the compute instance"
  type        = string
  default     = "llm-vm-instance"
}

variable "machine_type" {
  description = "The machine type for the compute instance"
  type        = string
  default     = "n1-standard-4"
}

variable "gpu_type" {
  description = "The type of GPU to attach to the instance"
  type        = string
}

variable "disk_size" {
  description = "The size of the boot disk in GB"
  type        = number
  default     = 100
}

variable "gpu_count" {
  description = "Number of GPUs to attach"
  type        = number
  default     = 1
}
