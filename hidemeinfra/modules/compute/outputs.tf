/**
 * # Compute Module Outputs
 *
 * Outputs from the compute module of the Hide Me application.
 */

output "instance_group" {
  description = "The instance group resource"
  value       = google_compute_region_instance_group_manager.app_instance_group.instance_group
}

output "instance_group_manager_id" {
  description = "The ID of the instance group manager"
  value       = google_compute_region_instance_group_manager.app_instance_group.id
}

output "instance_group_manager_self_link" {
  description = "The self link of the instance group manager"
  value       = google_compute_region_instance_group_manager.app_instance_group.self_link
}

output "instance_template_id" {
  description = "The ID of the instance template"
  value       = google_compute_instance_template.app_template.id
}

output "instance_template_self_link" {
  description = "The self link of the instance template"
  value       = google_compute_instance_template.app_template.self_link
}

output "health_check_id" {
  description = "The ID of the health check"
  value       = google_compute_health_check.app_health_check.id
}

output "health_check_self_link" {
  description = "The self link of the health check"
  value       = google_compute_health_check.app_health_check.self_link
}

output "autoscaler_id" {
  description = "The ID of the autoscaler"
  value       = google_compute_region_autoscaler.app_autoscaler.id
}

output "autoscaler_self_link" {
  description = "The self link of the autoscaler"
  value       = google_compute_region_autoscaler.app_autoscaler.self_link
}

output "app_port" {
  description = "The port on which the application serves traffic"
  value       = var.app_port
}

output "github_ssh_key_secret_id" {
  description = "The ID of the Secret Manager secret containing the GitHub SSH key"
  value       = google_secret_manager_secret.github_ssh_key.id
}

output "gemini_api_key_secret_id" {
  description = "The ID of the Secret Manager secret containing the Gemini API key"
  value       = google_secret_manager_secret.gemini_api_key.id
}

output "github_token_secret_id" {
  description = "The ID of the Secret Manager secret containing the GitHub Personal Access Token"
  value       = google_secret_manager_secret.github_token.id
}

output "server_ca_pem_secret_id" {
  description = "The ID of the Secret Manager secret containing the Cloud SQL server-ca.pem file"
  value       = google_secret_manager_secret.server_ca_pem.id
}

output "client_cert_pem_secret_id" {
  description = "The ID of the Secret Manager secret containing the Cloud SQL client-cert.pem file"
  value       = google_secret_manager_secret.client_cert_pem.id
}

output "client_key_pem_secret_id" {
  description = "The ID of the Secret Manager secret containing the Cloud SQL client-key.pem file"
  value       = google_secret_manager_secret.client_key_pem.id
}

# Update existing server_setup_instructions output
output "server_setup_instructions" {
  description = "Instructions for server setup"
  value       = <<-EOT
    The infrastructure is configured to automatically:

    1. Set up Docker and Docker Compose on each instance
    2. Configure Nginx as a reverse proxy with security enhancements
    3. Set up proper firewall rules with UFW
    4. Clone your GitHub repository (${var.github_repo})
       - Primary method: SSH key from Secret Manager
       - Fallback method: GitHub Personal Access Token
    5. Set up environment variables for your application
    6. Build and run your Docker containers

    The instances will be managed by an autoscaling group that maintains between ${var.min_instances} and ${var.max_instances} instances based on load.

    Health checks will monitor the /status endpoint on port ${var.app_port}.

    Your GitHub SSH key, GitHub token, and Gemini API key are stored securely in Secret Manager.

    For debugging repository access issues:
    - Check /opt/hide-me/startup-debug.log on the instances
    - Ensure either github_ssh_key or github_token variable is properly set in your tfvars file
  EOT
}