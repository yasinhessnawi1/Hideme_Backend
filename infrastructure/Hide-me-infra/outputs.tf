/**
 * # Main Outputs
 * 
 * This file contains all the outputs from the Hide Me application infrastructure.
 */

# VPC Outputs
output "network_id" {
  description = "The ID of the VPC network"
  value       = module.vpc.network_id
}

output "network_name" {
  description = "The name of the VPC network"
  value       = module.vpc.network_name
}


output "public_subnet_id" {
  description = "The ID of the public subnet"
  value       = module.vpc.public_subnet_id
}

output "private_subnet_id" {
  description = "The ID of the private subnet"
  value       = module.vpc.private_subnet_id
}

# Security Outputs
output "app_service_account_email" {
  description = "Email address of the application service account"
  value       = module.security.app_service_account_email
}

output "db_service_account_email" {
  description = "Email address of the database service account"
  value       = module.security.db_service_account_email
}

output "security_policy_name" {
  description = "Name of the Cloud Armor security policy"
  value       = module.security.security_policy_name
}

output "db_credentials_secret_id" {
  description = "ID of the secret containing database credentials"
  value       = module.security.db_credentials_secret_id
}

# Database Outputs
output "db_instance_name" {
  description = "The name of the database instance"
  value       = module.database.db_instance_name
}

output "db_connection_name" {
  description = "The connection name of the database instance"
  value       = module.database.connection_name
}

output "db_private_ip_address" {
  description = "The private IP address of the database instance"
  value       = module.database.private_ip_address
}

output "db_host" {
  description = "The hostname of the database instance"
  value = module.database.database_host
}

# Compute Outputs
output "instance_group" {
  description = "The instance group resource"
  value       = module.compute.instance_group
}

output "instance_template_id" {
  description = "The ID of the instance template"
  value       = module.compute.instance_template_id
}

output "app_port" {
  description = "The port on which the application serves traffic"
  value       = module.compute.app_port
}

output "assets_bucket_name" {
  description = "The name of the storage bucket for application assets"
  value       = module.compute.assets_bucket_name
}

output "github_ssh_key_secret_id" {
  description = "The ID of the Secret Manager secret containing the GitHub SSH key"
  value       = module.compute.github_ssh_key_secret_id
}

output "gemini_api_key_secret_id" {
  description = "The ID of the Secret Manager secret containing the Gemini API key"
  value       = module.compute.gemini_api_key_secret_id
}

# Load Balancer Outputs
output "load_balancer_ip" {
  description = "The static IP address of the load balancer"
  value       = module.load_balancer.lb_external_ip
}

output "load_balancer_name" {
  description = "The name of the load balancer"
  value       = module.load_balancer.lb_name
}

output "load_balancer_url" {
  description = "The URLs to access the application"
  value = {
    api_http  = "http://${var.domain}"
    api_https = "https://${var.domain}"
  }
}

# DNS Outputs (New)
output "dns_zone_name" {
  description = "The name of the Cloud DNS zone"
  value       = module.dns.dns_zone_name
}

output "dns_name_servers" {
  description = "The nameservers for the DNS zone (configure these at your domain registrar)"
  value       = module.dns.dns_name_servers
}

# Server Setup Outputs
output "server_setup_instructions" {
  description = "Information about the server setup"
  value       = module.compute.server_setup_instructions
}

# Deployment Instructions
output "deployment_instructions" {
  description = "Instructions for connecting your domain to the load balancer"
  value       = <<-EOT
    To connect your domain to the load balancer:

    1. In your Namecheap domain settings, update the nameservers to the following Google Cloud DNS nameservers:
       ${join("\n       ", module.dns.dns_name_servers)}

    2. Wait for DNS propagation (which can take up to 48 hours)

    3. Once DNS propagation is complete, SSL certificates will be automatically provisioned by Google

    4. Your application will be available at:
       - https://${var.domain} (main site)
       - https://www.${var.domain} (www subdomain)
       - https://api.${var.domain} (API endpoint)

    Note: Certificate provisioning may take up to 24 hours after DNS changes have propagated.
  EOT
}