/**
 * # VPC Module Outputs
 *
 * Outputs from the VPC module of the Hide Me application.
 */

output "network_id" {
  description = "The ID of the VPC network"
  value       = google_compute_network.vpc.id
}

output "network_name" {
  description = "The name of the VPC network"
  value       = google_compute_network.vpc.name
}

output "network_self_link" {
  description = "The self link of the VPC network"
  value       = google_compute_network.vpc.self_link
}

output "public_subnet_id" {
  description = "The ID of the public subnet"
  value       = google_compute_subnetwork.public_subnet.id
}

output "public_subnet_name" {
  description = "The name of the public subnet"
  value       = google_compute_subnetwork.public_subnet.name
}

output "public_subnet_cidr" {
  description = "The CIDR range of the public subnet"
  value       = google_compute_subnetwork.public_subnet.ip_cidr_range
}

output "private_subnet_id" {
  description = "The ID of the private subnet"
  value       = google_compute_subnetwork.private_subnet.id
}

output "private_subnet_name" {
  description = "The name of the private subnet"
  value       = google_compute_subnetwork.private_subnet.name
}

output "private_subnet_cidr" {
  description = "The CIDR range of the private subnet"
  value       = google_compute_subnetwork.private_subnet.ip_cidr_range
}

output "router_id" {
  description = "The ID of the Cloud Router"
  value       = google_compute_router.router.id
}

output "nat_gateway_id" {
  description = "The ID of the NAT gateway"
  value       = google_compute_router_nat.nat.id
}

output "private_dns_zone_id" {
  description = "The ID of the private DNS zone"
  value       = google_dns_managed_zone.private_zone.id
}

output "private_dns_zone_name" {
  description = "The name of the private DNS zone"
  value       = google_dns_managed_zone.private_zone.name
}
