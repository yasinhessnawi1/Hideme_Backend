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

# Create a firewall rule to allow health checks - SECURED
resource "google_compute_firewall" "allow_health_checks" {
  name        = "hide-me-allow-health-checks-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow health checks from Google Cloud health checking systems"

  allow {
    protocol = "tcp"
    ports    = [var.health_check_port]
  }

  source_ranges = var.health_check_ip_ranges

  target_tags = ["hide-me-app", "${var.environment}-app"]

  #tfsec:ignore:google-compute-no-public-ingress
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

  source_ranges = var.private_subnet_ranges
}

# Create a firewall rule to allow SSH access - SECURED
resource "google_compute_firewall" "allow_ssh" {
  name        = "hide-me-allow-ssh-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow SSH access to instances from IAP only"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.iap_ip_ranges

  target_tags = ["hide-me-app", "${var.environment}-app"]

  # tfsec:ignore:google-compute-no-public-ingress
}

# Create a firewall rule to allow backend access - SECURED
resource "google_compute_firewall" "allow_backend" {
  name        = "hide-me-allow-backend-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow access to backend services from load balancer"

  allow {
    protocol = "tcp"
    ports    = [var.backend_port, var.go_backend_port]
  }

  source_ranges = var.load_balancer_ip_ranges

  target_tags = ["hide-me-app", "${var.environment}-app"]

  # tfsec:ignore:google-compute-no-public-ingress
}

# Create a firewall rule to allow specific egress traffic - SECURED
resource "google_compute_firewall" "allow_specific_egress" {
  name        = "hide-me-allow-specific-egress-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Allow specific egress traffic to Google APIs"
  direction   = "EGRESS"

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  destination_ranges = var.google_api_ranges

  target_tags = ["hide-me-app", "${var.environment}-app"]

  # tfsec:ignore:google-compute-no-public-egress
}

# Add an explicit deny rule for all other egress traffic
resource "google_compute_firewall" "deny_all_egress" {
  name        = "hide-me-deny-all-egress-${var.environment}"
  project     = var.project
  network     = var.network_id
  description = "Deny all egress traffic not explicitly allowed"
  direction   = "EGRESS"
  priority    = 65534

  deny {
    protocol = "all"
  }

  destination_ranges = ["0.0.0.0/0"]

  target_tags = ["${var.environment}-deny-egress"]
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

# Create a Cloud Armor security policy with enhanced rules
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
        src_ip_ranges = var.allowed_ip_ranges
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
      ban_duration_sec = 300
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

  # Add additional protection rules
  rule {
    action   = "deny(403)"
    priority = "5000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('rce-stable')"
      }
    }
    description = "Remote Code Execution protection"
  }

  rule {
    action   = "deny(403)"
    priority = "6000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('lfi-stable')"
      }
    }
    description = "Local File Inclusion protection"
  }
}
