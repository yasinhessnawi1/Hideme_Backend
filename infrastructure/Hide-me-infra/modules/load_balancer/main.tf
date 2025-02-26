
# Create an unmanaged instance group containing the backend instance.
resource "google_compute_instance_group" "backend_group" {
  name    = "${var.instance_name}-ig"
  zone    = var.instance_zone
  project = var.project

  instances = [
    var.instance_self_link
  ]
}


# HTTP health check
resource "google_compute_health_check" "default" {
  name                = "${var.instance_name}-hc"
  check_interval_sec  = 5
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 2

  http_health_check {
    port         = var.backend_port
    request_path = "/"
  }
}

resource "google_compute_health_check" "tcp_health_check" {
  name                = "${var.instance_name}-tcp-hc"
  check_interval_sec  = 5
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 2

  tcp_health_check {
    port = 22
  }
}

resource "google_compute_backend_service" "tcp_backend" {
  name          = "${var.instance_name}-tcp-backend"
  protocol      = "TCP"
  timeout_sec   = 10
  health_checks = [google_compute_health_check.tcp_health_check.self_link]

  backend {
    group = google_compute_instance_group.backend_group.self_link
  }
}

# Define a backend service that uses the instance group.
resource "google_compute_backend_service" "default" {
  name          = "${var.instance_name}-backend"
  protocol      = "HTTP"
  port_name     = "http"
  timeout_sec   = 30
  health_checks = [google_compute_health_check.default.self_link]

  backend {
    group = google_compute_instance_group.backend_group.self_link
  }
}


# Create a URL map to direct incoming requests to the backend service.
resource "google_compute_url_map" "default" {
  name            = "${var.instance_name}-url-map"
  default_service = google_compute_backend_service.default.self_link
}


# Create a target HTTP proxy to route requests using the URL map.
resource "google_compute_target_http_proxy" "default" {
  name    = "${var.instance_name}-http-proxy"
  url_map = google_compute_url_map.default.self_link
}


# Reserve a global static IP address for the load balancer.
resource "google_compute_global_address" "default" {
  name    = "${var.instance_name}-lb-ip"
  project = var.project
}


# Create a global forwarding rule to route traffic to the target HTTP proxy.
resource "google_compute_global_forwarding_rule" "default" {
  name       = "${var.instance_name}-fwd-rule"
  project    = var.project
  target     = google_compute_target_http_proxy.default.self_link
  port_range = "80"
  ip_address = google_compute_global_address.default.address
}

# Firewall Rule for Backend Traffic
resource "google_compute_firewall" "allow_backend_traffic" {
  name    = "${var.instance_name}-allow-8000"
  project = var.project
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["8000"]
  }

  source_ranges = ["0.0.0.0/0"]  # Consider restricting this for security
  target_tags   = ["backend"]
}

