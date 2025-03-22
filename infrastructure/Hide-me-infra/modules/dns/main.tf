/**
 * # DNS Module
 *
 * This module creates DNS resources for the Hide Me application,
 * including Cloud DNS zone and records for the domain and SSL validation.
 */

# Create a Cloud DNS zone for the domain
resource "google_dns_managed_zone" "main_zone" {
  name        = "hide-me-zone-${var.environment}"
  project     = var.project
  dns_name    = "${var.domain_name}."
  description = "DNS zone for Hide Me domain ${var.domain_name}"

  visibility = "public"

  dnssec_config {
    state = "on"
  }

  labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create an A record for the apex domain (@ or root domain)
resource "google_dns_record_set" "apex_a_record" {
  name         = "${var.domain_name}."
  project      = var.project
  managed_zone = google_dns_managed_zone.main_zone.name
  type         = "A"
  ttl          = 300

  rrdatas = [var.load_balancer_ip]
}

# Create an A record for the API subdomain
resource "google_dns_record_set" "api_a_record" {
  name         = "${var.domain_name}."
  project      = var.project
  managed_zone = google_dns_managed_zone.main_zone.name
  type         = "A"
  ttl          = 300

  rrdatas = [var.load_balancer_ip]
}

# Create an A record for www subdomain
resource "google_dns_record_set" "www_a_record" {
  name         = "www.${var.domain_name}."
  project      = var.project
  managed_zone = google_dns_managed_zone.main_zone.name
  type         = "A"
  ttl          = 300

  rrdatas = [var.load_balancer_ip]
}

# Create MX records for email (if needed)
resource "google_dns_record_set" "mx_records" {
  name         = "${var.domain_name}."
  project      = var.project
  managed_zone = google_dns_managed_zone.main_zone.name
  type         = "MX"
  ttl          = 3600

  rrdatas = [
    "1 aspmx.l.google.com.",
    "5 alt1.aspmx.l.google.com.",
    "5 alt2.aspmx.l.google.com.",
    "10 alt3.aspmx.l.google.com.",
    "10 alt4.aspmx.l.google.com."
  ]
}

# Create TXT record for domain verification (for Google services, email verification, etc.)
resource "google_dns_record_set" "domain_verification" {
  name         = "${var.domain_name}."
  project      = var.project
  managed_zone = google_dns_managed_zone.main_zone.name
  type         = "TXT"
  ttl          = 3600

  rrdatas = [
    "\"v=spf1 include:_spf.google.com ~all\""
  ]
}

# Output the DNS nameservers that need to be configured at the domain registrar
output "nameservers" {
  description = "The nameservers for this zone that should be configured at the domain registrar"
  value       = google_dns_managed_zone.main_zone.name_servers
}