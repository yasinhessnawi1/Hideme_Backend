/**
 * # Load Balancer Module Outputs
 *
 * Outputs from the load balancer module of the Hide Me application.
 */

output "lb_external_ip" {
  description = "The static IP address of the load balancer"
  value       = google_compute_global_address.lb_static_ip.address
}

output "lb_name" {
  description = "The name of the load balancer (URL map name)"
  value       = google_compute_url_map.lb_url_map.name
}

output "lb_url_map_id" {
  description = "The ID of the URL map"
  value       = google_compute_url_map.lb_url_map.id
}

output "lb_url_map_self_link" {
  description = "The self link of the URL map"
  value       = google_compute_url_map.lb_url_map.self_link
}

output "lb_http_proxy_id" {
  description = "The ID of the HTTP target proxy"
  value       = google_compute_target_http_proxy.lb_http_proxy.id
}

output "lb_https_proxy_id" {
  description = "The ID of the HTTPS target proxy"
  value       = google_compute_target_https_proxy.lb_https_proxy.id
}

output "lb_backend_service_id" {
  description = "The ID of the backend service"
  value       = google_compute_backend_service.lb_backend_service.id
}

output "lb_backend_service_self_link" {
  description = "The self link of the backend service"
  value       = google_compute_backend_service.lb_backend_service.self_link
}

output "lb_forwarding_rules" {
  description = "The IDs of all forwarding rules"
  value = {
    http  = google_compute_global_forwarding_rule.lb_http_forwarding_rule.id
    https = google_compute_global_forwarding_rule.lb_https_forwarding_rule.id
  }
}

output "static_ip_id" {
  description = "The ID of the static IP address resource"
  value       = google_compute_global_address.lb_static_ip.id
}

output "static_ip_name" {
  description = "The name of the static IP address resource"
  value       = google_compute_global_address.lb_static_ip.name
}

output "ssl_certificates" {
  description = "The IDs of the Google-managed SSL certificates"
  value = {
    api    = google_compute_managed_ssl_certificate.api_certificate.id
    go_api = google_compute_managed_ssl_certificate.go_api_certificate.id
  }
}

output "ssl_certificate_domains" {
  description = "The domains configured for SSL certificates"
  value = {
    api    = google_compute_managed_ssl_certificate.api_certificate.managed[0].domains
    go_api = google_compute_managed_ssl_certificate.go_api_certificate.managed[0].domains
  }
}

output "health_check_id" {
  description = "The ID of the health check for the load balancer"
  value       = google_compute_health_check.lb_health_check.id
}

output "domain_name" {
  description = "The domain name used for the load balancer"
  value       = var.domain_name
}

output "lb_urls" {
  description = "The URLs for accessing the application"
  value = {
    http_api     = "http://api.${var.domain_name}"
    https_api    = "https://api.${var.domain_name}"
    http_go_api  = "http://goapi.${var.domain_name}"
    https_go_api = "https://goapi.${var.domain_name}"
  }
}