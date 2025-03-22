/**
 * # Database Module Outputs
 *
 * Outputs from the database module of the Hide Me application.
 */

output "db_instance_name" {
  description = "The name of the database instance"
  value       = google_sql_database_instance.postgres.name
}

output "db_instance_id" {
  description = "The ID of the database instance"
  value       = google_sql_database_instance.postgres.id
}

output "connection_name" {
  description = "The connection name of the database instance used in connection strings"
  value       = google_sql_database_instance.postgres.connection_name
}

output "private_ip_address" {
  description = "The private IP address of the database instance"
  value       = google_sql_database_instance.postgres.private_ip_address
}

output "db_name" {
  description = "The name of the database"
  value       = google_sql_database.database.name
}

output "db_user" {
  description = "The name of the database user"
  value       = google_sql_user.user.name
}

output "read_replica_instance_name" {
  description = "The name of the read replica instance (if created)"
  value       = var.environment == "prod" ? google_sql_database_instance.read_replica[0].name : null
}

output "read_replica_connection_name" {
  description = "The connection name of the read replica instance (if created)"
  value       = var.environment == "prod" ? google_sql_database_instance.read_replica[0].connection_name : null
}

output "read_replica_private_ip_address" {
  description = "The private IP address of the read replica instance (if created)"
  value       = var.environment == "prod" ? google_sql_database_instance.read_replica[0].private_ip_address : null
}
