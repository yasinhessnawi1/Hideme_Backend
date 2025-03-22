/**
 * # Security Module
 *
 * This module creates security resources for the Hide Me application,
 * including firewall rules, service accounts, and security policies.
 */

# Create a service account for the application
resource "google_service_account" "app_service_account" {
  project      = var.project
  account_id   = "hide-me-app-${var.environment}"
  display_name = "Hide Me Application Service Account (${var.environment})"
  description  = "Service account for the Hide Me application instances"
}

# Create a service account for the database
resource "google_service_account" "db_service_account" {
  project      = var.project
  account_id   = "hide-me-db-${var.environment}"
  display_name = "Hide Me Database Service Account (${var.environment})"
  description  = "Service account for the Hide Me database instances"
}

# Grant necessary roles to the application service account
resource "google_project_iam_member" "app_service_account_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/secretmanager.secretAccessor",
    "roles/cloudsql.client"
  ])

  project = var.project
  role    = each.key
  member  = "serviceAccount:${google_service_account.app_service_account.email}"
}

# Grant necessary roles to the database service account
resource "google_project_iam_member" "db_service_account_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudsql.editor"
  ])

  project = var.project
  role    = each.key
  member  = "serviceAccount:${google_service_account.db_service_account.email}"
}

# Create a firewall rule to allow health checks
resource "google_compute_firewall" "allow_health_checks" {
  name        = "hide-me-allow-health-checks-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow health checks from Google Cloud health checking systems"

  allow {
    protocol = "tcp"
    ports    = [var.health_check_port]
  }

  # Health check systems
  source_ranges = [
    "35.191.0.0/16",
    "130.211.0.0/22",
    "209.85.152.0/22",
    "209.85.204.0/22"
  ]

  target_tags = ["hide-me-app", "${var.environment}-app"]
}

# Create a firewall rule to allow internal communication
resource "google_compute_firewall" "allow_internal" {
  name        = "hide-me-allow-internal-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow internal communication between instances"

  allow {
    protocol = "tcp"
  }

  allow {
    protocol = "udp"
  }

  allow {
    protocol = "icmp"
  }

  # Private subnet ranges
  source_ranges = var.private_subnet_ranges
}

# Create a firewall rule to allow SSH access
resource "google_compute_firewall" "allow_ssh" {
  name        = "hide-me-allow-ssh-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow SSH access to instances"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP IP ranges for SSH
  source_ranges = ["35.235.240.0/20"]

  target_tags = ["hide-me-app", "${var.environment}-app"]
}

# Create a firewall rule to allow backend access
resource "google_compute_firewall" "allow_backend" {
  name        = "hide-me-allow-backend-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow access to backend services"

  allow {
    protocol = "tcp"
    ports    = [var.backend_port]
  }

  # Load balancer IP ranges
  source_ranges = [
    "130.211.0.0/22",
    "35.191.0.0/16"
  ]

  target_tags = ["hide-me-app", "${var.environment}-app"]
}

# Create a firewall rule to allow specific egress traffic
resource "google_compute_firewall" "allow_specific_egress" {
  name        = "hide-me-allow-specific-egress-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow specific egress traffic"
  direction   = "EGRESS"

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  # Google APIs and services
  destination_ranges = [
    "199.36.153.8/30", # Restricted Google APIs
    "199.36.153.4/30"  # Private Google Access
  ]

  target_tags = ["hide-me-app", "${var.environment}-app"]
}

# Create a Secret Manager secret for database credentials
resource "google_secret_manager_secret" "db_credentials" {
  project   = var.project
  secret_id = "hide-me-db-credentials-${var.environment}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# Store database credentials in Secret Manager
resource "google_secret_manager_secret_version" "db_credentials_version" {
  secret = google_secret_manager_secret.db_credentials.id
  secret_data = jsonencode({
    username = var.db_user
    password = var.db_password
    database = var.db_name
  })
}

# Create a Cloud Armor security policy
resource "google_compute_security_policy" "security_policy" {
  name        = "hide-me-security-policy-${var.environment}"
  project     = var.project
  description = "Security policy for Hide Me application"

  # Default rule (deny all)
  rule {
    action   = "deny(403)"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default deny rule"
  }

  # Allow rule for legitimate traffic
  rule {
    action   = "allow"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["0.0.0.0/0"]
      }
    }
    description = "Allow legitimate traffic"
  }

  # Rate limiting rule
  rule {
    action   = "rate_based_ban"
    priority = "2000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Rate limiting rule"
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
      ban_duration_sec = 300 # 5 minutes ban duration
    }
  }

  # XSS protection
  rule {
    action   = "deny(403)"
    priority = "3000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-stable')"
      }
    }
    description = "XSS protection"
  }

  # SQL injection protection
  rule {
    action   = "deny(403)"
    priority = "4000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-stable')"
      }
    }
    description = "SQL injection protection"
  }
}
