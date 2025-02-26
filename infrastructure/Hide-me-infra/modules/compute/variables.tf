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


variable "instance_name" {
  description = "The name of the compute instance"
  type        = string
  default     = "llm-vm-instance"
}

variable "machine_type" {
  description = "The machine type for the compute instance. Allowed values: g2-standard-8, g2-standard-12, g2-standard-16, g2-standard-24, g2-standard-32"
  type        = string
  default     = "g2-standard-4"
  validation {
    condition     = contains(["c2-standard-8","g2-standard-4", "g2-standard-8", "g2-standard-12", "g2-standard-16", "g2-standard-32"], var.machine_type)
    error_message = "machine_type must be one of: g2-standard-8, g2-standard-12, g2-standard-16, g2-standard-24, or g2-standard-32."
  }
}
/*
variable "gpu_type" {
  description = "The GPU type to attach to the instance (set to NVIDIA L4)."
  type        = string
  default     = "nvidia-l4"
}
*/
variable "disk_size" {
    description = "The size of the boot disk in GB"
    type        = number
    default     = 100
}

variable "gpu_count" {
  description = "The number of GPUs to attach"
  type        = number
  default     = 0
}

variable "subnetwork" {
  description = "The subnetwork to attach the instance"
  type        = string
}

# New variables for SSH key–based access

variable "use_ssh_keys" {
  description = "Whether to inject SSH keys via metadata (true) or use OS Login (false)"
  type        = bool
  default     = true
}

variable "ssh_user" {
  description = "The username for SSH access"
  type        = string
  default     = "ubuntu"  # Adjust this as needed
}

variable "ssh_public_key_file" {
  description = "Path to the SSH public key file"
  type        = string
  default     = "~/.ssh/id_rsa.pub"  # Adjust the path as needed
}
