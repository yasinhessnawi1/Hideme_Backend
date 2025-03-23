/**
 * # Monitoring Module Outputs
 *
 * Outputs from the monitoring module of the Hide Me application.
 */

output "notification_channel_id" {
  description = "The ID of the notification channel (if created)"
  value       = var.alert_email != "" ? google_monitoring_notification_channel.email_channel[0].id : null
}

output "cpu_alert_policy_id" {
  description = "The ID of the CPU utilization alert policy"
  value       = google_monitoring_alert_policy.cpu_utilization_alert.id
}

output "memory_alert_policy_id" {
  description = "The ID of the memory utilization alert policy"
  value       = google_monitoring_alert_policy.memory_utilization_alert.id
}

output "disk_alert_policy_id" {
  description = "The ID of the disk utilization alert policy"
  value       = google_monitoring_alert_policy.disk_utilization_alert.id
}

output "db_cpu_alert_policy_id" {
  description = "The ID of the database CPU utilization alert policy"
  value       = google_monitoring_alert_policy.db_cpu_utilization_alert.id
}

output "db_memory_alert_policy_id" {
  description = "The ID of the database memory utilization alert policy"
  value       = google_monitoring_alert_policy.db_memory_utilization_alert.id
}

output "db_disk_alert_policy_id" {
  description = "The ID of the database disk utilization alert policy"
  value       = google_monitoring_alert_policy.db_disk_utilization_alert.id
}

output "lb_latency_alert_policy_id" {
  description = "The ID of the load balancer latency alert policy"
  value       = google_monitoring_alert_policy.lb_latency_alert.id
}

output "lb_error_rate_alert_policy_id" {
  description = "The ID of the load balancer error rate alert policy"
  value       = google_monitoring_alert_policy.lb_error_rate_alert.id
}

output "app_dashboard_id" {
  description = "The ID of the application dashboard"
  value       = google_monitoring_dashboard.app_dashboard.id
}

