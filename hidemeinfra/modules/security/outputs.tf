/**
 * # Security Module Outputs
 *
 * Outputs from the security module of the Hide Me application.
 */

output "app_service_account_email" {
  description = "Email address of the application service account"
  value       = google_service_account.app_service_account.email
}

output "app_service_account_id" {
  description = "ID of the application service account"
  value       = google_service_account.app_service_account.id
}

output "db_service_account_email" {
  description = "Email address of the database service account"
  value       = google_service_account.db_service_account.email
}

output "db_service_account_id" {
  description = "ID of the database service account"
  value       = google_service_account.db_service_account.id
}

output "db_credentials_secret_id" {
  description = "ID of the secret containing database credentials"
  value       = google_secret_manager_secret.db_credentials.id
}


output "security_policy_id" {
  description = "ID of the Cloud Armor security policy"
  value       = google_compute_security_policy.security_policy.id
}

output "security_policy_name" {
  description = "Name of the Cloud Armor security policy"
  value       = google_compute_security_policy.security_policy.name
}



output "service_account_email" {
  description = "Email address of the application service account (alias for app_service_account_email)"
  value       = google_service_account.app_service_account.email
}
