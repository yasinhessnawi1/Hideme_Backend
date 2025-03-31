/**
 * # VPC Module
 *
 * This module creates a Virtual Private Cloud (VPC) network with public and private subnets
 * for the Hide Me application, implementing network security best practices.
 */

# Create the VPC network
resource "google_compute_network" "vpc" {
  name                    = "${var.network_name}-${var.environment}"
  project                 = var.project
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

# Create a public subnet for load balancers and bastion hosts
resource "google_compute_subnetwork" "public_subnet" {
  name          = "${var.network_name}-public-${var.environment}"
  project       = var.project
  ip_cidr_range = var.public_subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc.id

  # Enable Private Google Access for services
  private_ip_google_access = true
}

# Create a private subnet for application and database instances
resource "google_compute_subnetwork" "private_subnet" {
  name          = "${var.network_name}-private-${var.environment}"
  project       = var.project
  ip_cidr_range = var.private_subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc.id

  # Enable Private Google Access for services
  private_ip_google_access = true
}

# Create a Cloud Router for NAT gateway
resource "google_compute_router" "router" {
  name    = "${var.network_name}-router-${var.environment}"
  project = var.project
  region  = var.region
  network = google_compute_network.vpc.id

  bgp {
    asn = 64514
  }
}

# Create a NAT gateway for private instances to access the internet
resource "google_compute_router_nat" "nat" {
  name                               = "${var.network_name}-nat-${var.environment}"
  project                            = var.project
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.private_subnet.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}

# Create a global address for Private Service Connect
resource "google_compute_global_address" "private_service_connect" {
  name          = "${var.network_name}-psc-${var.environment}"
  project       = var.project
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

# Create a Private Service Connect endpoint for Google APIs
resource "google_service_networking_connection" "private_service_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_connect.name]
}

# Create a DNS zone for internal services
resource "google_dns_managed_zone" "private_zone" {
  name        = "hide-me-internal-${var.environment}"
  project     = var.project
  dns_name    = "internal.hide-me.${var.environment}."
  description = "Private DNS zone for Hide Me internal services"

  visibility = "private"

  private_visibility_config {
    networks {
      network_url = google_compute_network.vpc.id
    }
  }
}

# Create a DNS policy to control outbound DNS
resource "google_dns_policy" "default" {
  name        = "hide-me-dns-policy-${var.environment}"
  project     = var.project
  description = "DNS policy for Hide Me application"

  enable_inbound_forwarding = false

  networks {
    network_url = google_compute_network.vpc.id
  }

  # Force all DNS queries through Google's DNS servers
  alternative_name_server_config {
    target_name_servers {
      ipv4_address = "8.8.8.8"
    }
    target_name_servers {
      ipv4_address = "8.8.4.4"
    }
  }
}
