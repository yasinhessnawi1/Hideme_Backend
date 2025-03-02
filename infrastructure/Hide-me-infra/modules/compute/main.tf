resource "google_compute_address" "static_ip" {
  name   = "${var.instance_name}-static-ip"
  project = var.project
  region  = var.region
}

# Create the Compute Engine instance.
resource "google_compute_instance" "vm_instance" {
  name         = var.instance_name
  machine_type = var.machine_type
  zone         = var.zone
  project      = var.project

  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2004-lts"  # Change to your preferred OS image.
      size = var.disk_size  # Disk size in GB.
    }
  }

  network_interface {
    subnetwork = var.subnetwork
    access_config {
      nat_ip = google_compute_address.static_ip.address
    }
  }

  # Attach a GPU accelerator.
  /*
  guest_accelerator {
    type  = var.gpu_type
    count = var.gpu_count
  }

   */

  metadata_startup_script = <<EOT
#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Update packages
sudo apt update && sudo apt upgrade -y

# Install UFW if not installed
sudo apt install -y ufw

# Enable UFW
sudo ufw --force enable
sudo ufw enable
# Allow traffic on port 8000
sudo ufw allow 8000/tcp

# Allow SSH access to prevent being locked out
sudo ufw allow OpenSSH

# Reload UFW to apply rules
sudo ufw reload

# Confirm UFW status
sudo ufw status verbose
EOT


  scheduling {
    on_host_maintenance = "TERMINATE"
    automatic_restart   = false
  }
  shielded_instance_config {
    enable_integrity_monitoring = true
    enable_vtpm = true

  }


  metadata = merge(

      var.use_ssh_keys ? {
      "block-project-ssh-keys" = "FALSE"
      # When using SSH keys, disable OS Login and inject the key.
      "enable-oslogin" = "FALSE",
      "ssh-keys"       =   "${var.ssh_user}:${trim(file("~/.ssh/id_rsa.pub"), "\n")}"

    } : {
      "block-project-ssh-keys" = "TRUE"
      # Otherwise, leave OS Login enabled.
      "enable-oslogin" = "TRUE"
    }
  )

  tags = ["allow-ssh-http"]
}

