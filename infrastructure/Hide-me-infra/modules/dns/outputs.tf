/**
 * # DNS Module Outputs
 *
 * Outputs from the DNS module of the Hide Me application.
 */

output "dns_zone_id" {
  description = "The ID of the DNS zone"
  value       = google_dns_managed_zone.main_zone.id
}

output "dns_zone_name" {
  description = "The name of the DNS zone"
  value       = google_dns_managed_zone.main_zone.name
}

output "dns_name_servers" {
  description = "The name servers for the DNS zone"
  value       = google_dns_managed_zone.main_zone.name_servers
}

output "api_dns_record" {
  description = "The API DNS record"
  value       = google_dns_record_set.api_a_record.name
}

output "apex_dns_record" {
  description = "The apex DNS record"
  value       = google_dns_record_set.apex_a_record.name
}

output "www_dns_record" {
  description = "The www DNS record"
  value       = google_dns_record_set.www_a_record.name
}