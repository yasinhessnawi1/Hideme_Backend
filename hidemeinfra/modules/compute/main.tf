/**
 * # Compute Module
 *
 * This module creates compute resources for the Hide Me application,
 * integrating with the existing backend deployment via Docker.
 */

# Create an instance template for the application servers
# Create an instance template for the application servers
resource "google_compute_instance_template" "app_template" {
  name_prefix  = "${var.instance_name}-template-1-0-0-"
  project      = var.project
  machine_type = var.machine_type
  region       = var.region
  # Use a service account with minimal permissions
  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  # Boot disk with Ubuntu LTS
  disk {
    source_image = "ubuntu-os-cloud/ubuntu-2004-lts"
    auto_delete  = true
    boot         = true
    disk_size_gb = var.disk_size
    disk_type    = var.disk_type
  }

  # Network interface in the private subnet
  network_interface {
    network    = var.network_id
    subnetwork = var.subnet_id

    # Add access config for GitHub Actions access
    access_config {
      # Ephemeral IP - needed for initial setup and GitHub Actions access
    }
  }

  # Metadata for startup script and SSH keys
  metadata = {
    startup-script = templatefile("${path.module}/scripts/startup.sh", {
      port                   = var.app_port
      go_port                = var.go_port
      env                    = var.environment
      repo                   = var.github_repo
      go_repo                = var.go_github_repo
      branch                 = var.github_branch
      dbuser                 = var.db_user
      dbpass                 = var.db_password
      dbname                 = var.db_name
      dbport                 = var.db_port
      dbhost                 = var.db_host
      dbconn                 = var.db_connection_name
      gemini_api_key         = var.gemini_api_key
      GITHUB_TOKEN           = var.github_token
      REPO_PATH              = var.github_repo
      REPO_OWNER             = var.repo_owner
      REPO_NAME              = var.repo_name
      domain                 = var.domain
      go_domain              = var.go_domain
      ssl_email              = var.ssl_email
      SENDGRID_API_KEY       = var.SENDGRID_API_KEY
      API_KEY_ENCRYPTION_KEY = var.API_KEY_ENCRYPTION_KEY
    })
    enable-oslogin = "TRUE"
  }

  # Tags for firewall rules
  tags = ["hide-me-app", "${var.environment}-app"]

  # Ensure proper shutdown for instances
  scheduling {
    automatic_restart   = var.environment == "prod"
    on_host_maintenance = var.environment == "prod" ? "MIGRATE" : "TERMINATE"
    preemptible         = var.environment != "prod" # Use preemptible VMs in non-prod for cost savings
  }

  # Enable shielded VM security features
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # Set a short lifecycle to recreate templates when changed
  lifecycle {
    create_before_destroy = true
  }
}

# Create a health check for the instance group
resource "google_compute_health_check" "app_health_check" {
  name                = "${var.instance_name}-health-check"
  project             = var.project
  check_interval_sec  = 5
  timeout_sec         = 5
  healthy_threshold   = 3
  unhealthy_threshold = 3

  http_health_check {
    port         = var.app_port
    request_path = "/status"
  }
}

# Create a regional managed instance group for high availability
resource "google_compute_region_instance_group_manager" "app_instance_group" {
  name                      = "${var.instance_name}-instance-group-manager"
  project                   = var.project
  region                    = var.region
  base_instance_name        = var.instance_name
  distribution_policy_zones = var.zones

  version {
    instance_template = google_compute_instance_template.app_template.id
  }

  # Configure auto-healing with the health check
  auto_healing_policies {
    health_check      = google_compute_health_check.app_health_check.id
    initial_delay_sec = 600
  }

  # Configure update policy for rolling updates
  update_policy {
    type                         = "PROACTIVE"
    instance_redistribution_type = "PROACTIVE"
    minimal_action               = "REPLACE"
    max_surge_fixed              = 2
    max_unavailable_fixed        = 0
    replacement_method           = "SUBSTITUTE"
  }

  # Configure named ports for load balancing
  named_port {
    name = "http"
    port = var.app_port
  }

  named_port {
    name = "gohttp"
    port = var.go_port
  }

  # Add target pools if needed
  target_pools = var.target_pools
  /*
    # Wait for instances to be created before returning
    wait_for_instances = true

   */
}

# Create an autoscaler for the instance group
resource "google_compute_region_autoscaler" "app_autoscaler" {
  name    = "${var.instance_name}-autoscaler"
  project = var.project
  region  = var.region
  target  = google_compute_region_instance_group_manager.app_instance_group.id

  autoscaling_policy {
    max_replicas    = var.max_instances
    min_replicas    = var.min_instances
    cooldown_period = 60

    # CPU utilization based scaling
    cpu_utilization {
      target = 0.7 # Target CPU utilization of 70%
    }

    # HTTP load based scaling
    load_balancing_utilization {
      target = 0.8 # Target load balancing utilization of 80%
    }

    # Scale in controls to prevent rapid scale-in
    scale_in_control {
      time_window_sec = 300
      max_scaled_in_replicas {
        fixed = 1
      }
    }
  }
}


# Create a Secret Manager secret for GitHub SSH key
resource "google_secret_manager_secret" "github_ssh_key" {
  project   = var.project
  secret_id = "hide-me-github-ssh-key-${var.environment}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# Store GitHub SSH key in Secret Manager
resource "google_secret_manager_secret_version" "github_ssh_key_version" {
  secret      = google_secret_manager_secret.github_ssh_key.id
  secret_data = var.github_ssh_key
}

# Create a Secret Manager secret for Gemini API key
resource "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project
  secret_id = "hide-me-gemini-api-key-${var.environment}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# Store Gemini API key in Secret Manager
resource "google_secret_manager_secret_version" "gemini_api_key_version" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key
}

resource "google_secret_manager_secret" "github_token" {
  project   = var.project
  secret_id = "hide-me-github-token-${var.environment}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# Store GitHub token in Secret Manager
resource "google_secret_manager_secret_version" "github_token_version" {
  count       = var.github_token != "" ? 1 : 0
  secret      = google_secret_manager_secret.github_token.id
  secret_data = var.github_token
}

# === Cloud SQL Certificate Secrets ===
resource "google_secret_manager_secret" "server_ca_pem" {
  project   = var.project
  secret_id = "hide-me-server-ca-pem-${var.environment}"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "server_ca_pem_version" {
  secret      = google_secret_manager_secret.server_ca_pem.id
  secret_data = var.server_ca_pem
}

resource "google_secret_manager_secret" "client_cert_pem" {
  project   = var.project
  secret_id = "hide-me-client-cert-pem-${var.environment}"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "client_cert_pem_version" {
  secret      = google_secret_manager_secret.client_cert_pem.id
  secret_data = var.client_cert_pem
}

resource "google_secret_manager_secret" "client_key_pem" {
  project   = var.project
  secret_id = "hide-me-client-key-pem-${var.environment}"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "client_key_pem_version" {
  secret      = google_secret_manager_secret.client_key_pem.id
  secret_data = var.client_key_pem
}