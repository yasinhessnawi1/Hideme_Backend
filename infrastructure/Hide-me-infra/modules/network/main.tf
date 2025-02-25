resource "google_compute_network" "vpc_network" {
  name                    = var.network_name
  project                 = var.project
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.network_name}-subnet"
  ip_cidr_range = "10.0.0.0/16"
  region        = var.region
  network       = google_compute_network.vpc_network.id
  project       = var.project
  secondary_ip_range {
    range_name    = "tf-test-secondary-range-update1"
    ip_cidr_range = "192.168.10.0/24"
  }
  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "default" {
  name    = "${var.network_name}-fw"
  network = google_compute_network.vpc_network.id
  project = var.project

  allow {
    protocol = "tcp"
    ports    = ["22", "80", "443"]
  }
  # Restricting source IPs is recommended in production.
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["allow-ssh-http"]
}
