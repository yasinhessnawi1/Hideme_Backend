/**
 * # Load Balancer Module
 *
 * This module creates load balancing resources for the Hide Me application,
 * including a global HTTP(S) load balancer with Cloud Armor security policy.
 */

# Create a static IP address for the load balancer
resource "google_compute_global_address" "lb_static_ip" {
  name        = var.static_ip_name
  project     = var.project
  description = "Static IP address for Hide Me load balancer"
}

# Create a Google-managed SSL certificate for the root domain
resource "google_compute_managed_ssl_certificate" "root_certificate" {
  name    = "hide-me-root-ssl-cert-${var.environment}"
  project = var.project

  managed {
    domains = [var.domain_name, "www.${var.domain_name}"]
  }
}

# Create a Google-managed SSL certificate for the API subdomain
resource "google_compute_managed_ssl_certificate" "api_certificate" {
  name    = "hide-me-api-ssl-cert-${var.environment}"
  project = var.project

  managed {
    domains = ["${var.domain_name}"]
  }
}

# Create a health check for the backend service
resource "google_compute_health_check" "lb_health_check" {
  name                = "hide-me-lb-health-check-${var.environment}"
  project             = var.project
  check_interval_sec  = 5
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = var.health_check_port
    request_path = "/status"
  }
}

# Create a backend service for the load balancer
resource "google_compute_backend_service" "lb_backend_service" {
  name                  = "hide-me-backend-service-${var.environment}"
  project               = var.project
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 300
  health_checks         = [google_compute_health_check.lb_health_check.id]
  load_balancing_scheme = "EXTERNAL_MANAGED"

  # Attach security policy if provided
  security_policy = var.security_policy_name != "" ? var.security_policy_name : null

  # Configure backend
  backend {
    group           = var.instance_group
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
    max_utilization = 0.8
  }

  # Configure connection draining
  connection_draining_timeout_sec = 300
}

# Create a URL map for the load balancer
resource "google_compute_url_map" "lb_url_map" {
  name            = "hide-me-url-map-${var.environment}"
  project         = var.project
  default_service = google_compute_backend_service.lb_backend_service.id
}

# Create an HTTP target proxy
resource "google_compute_target_http_proxy" "lb_http_proxy" {
  name    = "hide-me-http-proxy-${var.environment}"
  project = var.project
  url_map = google_compute_url_map.lb_url_map.id
}

# Create an HTTPS target proxy with API certificate
resource "google_compute_target_https_proxy" "lb_https_api_proxy" {
  name             = "hide-me-https-api-proxy-${var.environment}"
  project          = var.project
  url_map          = google_compute_url_map.lb_url_map.id
  ssl_certificates = [google_compute_managed_ssl_certificate.api_certificate.id]
}

# Create an HTTPS target proxy with root domain certificate
resource "google_compute_target_https_proxy" "lb_https_root_proxy" {
  name             = "hide-me-https-root-proxy-${var.environment}"
  project          = var.project
  url_map          = google_compute_url_map.lb_url_map.id
  ssl_certificates = [google_compute_managed_ssl_certificate.root_certificate.id]
}

# Create an HTTP forwarding rule for all domains (will redirect to HTTPS)
resource "google_compute_global_forwarding_rule" "lb_http_forwarding_rule" {
  name                  = "hide-me-http-forwarding-rule-${var.environment}"
  project               = var.project
  target                = google_compute_target_http_proxy.lb_http_proxy.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_static_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# Create an HTTPS forwarding rule for API subdomain
resource "google_compute_global_forwarding_rule" "lb_https_api_forwarding_rule" {
  name                  = "hide-me-https-api-forwarding-rule-${var.environment}"
  project               = var.project
  target                = google_compute_target_https_proxy.lb_https_api_proxy.id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb_static_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"


}
